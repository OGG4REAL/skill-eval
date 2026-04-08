"""
RuleScorer
Phase 1 最小规则评分器 + Phase 2 task-aware 评分入口

Phase 1 评分项（旧路径 score()）：
- task_success: 是否成功完成
- tool_efficiency: 工具调用效率
- artifact_completeness: 产物完整性
- trajectory_quality: 轨迹质量启发式

Phase 2 评分项（新路径 score_task_run()）：
- task_success: 基础成功 + pass_criteria 硬约束
- signal_match: expected_signals 命中 + forbidden_signals 扣分
- artifact_match: expected_artifacts glob 匹配
- tool_efficiency: 工具调用效率（复用旧逻辑）
- trajectory_quality: 过程健康度（复用旧逻辑）
"""
from __future__ import annotations

import fnmatch
import posixpath
from typing import Any, Dict, List, Optional, Tuple

from .models import EvalRecord, RunRecord


class RuleScorer:
    """基于规则的评分器，同时兼容 Phase 1 旧路径和 Phase 2 task-aware 路径"""

    @staticmethod
    def _normalize_workspace_path(path: str) -> str:
        """将相对工作区路径统一映射到逻辑 /workspace/... 口径。"""
        if not isinstance(path, str) or not path:
            return path

        normalized = path.replace("\\", "/")
        if normalized == "/workspace":
            return normalized
        if normalized.startswith("/workspace/"):
            return posixpath.normpath(normalized)
        if normalized.startswith("/"):
            return normalized

        normalized = normalized.lstrip("./")
        return posixpath.normpath(f"/workspace/{normalized}")

    @classmethod
    def _normalize_workspace_pattern(cls, pattern: str) -> str:
        """保留 glob 通配符，统一 pattern 的工作区前缀口径。"""
        if not isinstance(pattern, str) or not pattern:
            return pattern

        normalized = pattern.replace("\\", "/")
        if normalized == "/workspace":
            return normalized
        if normalized.startswith("/workspace/") or normalized.startswith("/"):
            return normalized

        normalized = normalized.lstrip("./")
        return f"/workspace/{normalized}"

    # ── Phase 1 旧路径（保持不变） ───────────────────────────

    def score(self, run: RunRecord, artifacts: List[str]) -> EvalRecord:
        """
        对一次 run 生成评估结果（Phase 1 路径）。
        评分失败不影响主流程——异常时返回降级结果。
        """
        try:
            scores = {
                "task_success": self._score_task_success(run),
                "tool_efficiency": self._score_tool_efficiency(run),
                "artifact_completeness": self._score_artifact_completeness(run, artifacts),
                "trajectory_quality": self._score_trajectory_quality(run),
            }
            metrics = {
                "duration_ms": run.duration_ms,
                "iterations": run.iterations,
                "tool_calls": run.tool_calls,
                "tool_errors": run.tool_errors,
                "files_generated": len(artifacts),
            }
            notes: List[str] = []
            if run.tool_errors > 0:
                notes.append(f"存在 {run.tool_errors} 次工具调用失败")
            if run.iterations >= 10:
                notes.append(f"迭代次数较多: {run.iterations}")

            return EvalRecord(
                run_id=run.run_id,
                task_id=run.task_id,
                variant_id=run.variant_id,
                status=run.status,
                metrics=metrics,
                scores=scores,
                notes=notes,
            )
        except Exception as e:
            return EvalRecord(
                run_id=run.run_id,
                task_id=run.task_id,
                variant_id=run.variant_id,
                status=run.status,
                metrics={},
                scores={
                    "task_success": None,
                    "tool_efficiency": None,
                    "artifact_completeness": None,
                    "trajectory_quality": None,
                },
                notes=[f"评分异常: {e}"],
            )

    # ── Phase 2 task-aware 路径 ──────────────────────────────

    def score_task_run(
        self,
        task: dict,
        run: RunRecord,
        trajectory: List[dict],
        artifacts: List[str],
        final_response_present: bool,
    ) -> EvalRecord:
        """
        Task-aware 评分入口（benchmark 路径）。

        消费 TaskLoader 输出的 task dict，结合 run metadata、trajectory 事件、
        artifact 列表和 final_response_present 标志，产出可解释的 EvalRecord。

        task_id 优先取 task["task_id"]，run.task_id 仅作兜底。
        异常时返回降级 EvalRecord，不抛出，保障批量 benchmark 稳定性。
        """
        task_id = task.get("task_id") or run.task_id

        try:
            return self._score_task_run_inner(
                task, run, trajectory, artifacts, final_response_present, task_id
            )
        except Exception as e:
            return EvalRecord(
                run_id=run.run_id,
                task_id=task_id,
                variant_id=run.variant_id,
                status=run.status,
                metrics={},
                scores={
                    "task_success": None,
                    "signal_match": None,
                    "artifact_match": None,
                    "tool_efficiency": None,
                    "trajectory_quality": None,
                },
                notes=[f"评分异常: {e}"],
            )

    def _score_task_run_inner(
        self,
        task: dict,
        run: RunRecord,
        trajectory: List[dict],
        artifacts: List[str],
        final_response_present: bool,
        task_id: str,
    ) -> EvalRecord:
        notes: List[str] = []
        detail_metrics: Dict[str, Any] = {}

        # 1. pass_criteria 硬约束
        criteria_ok, criteria_notes, criteria_detail = self._evaluate_pass_criteria(
            task, run, final_response_present
        )
        notes.extend(criteria_notes)
        detail_metrics["pass_criteria"] = criteria_detail

        # 2. task_success
        task_success = self._score_task_success_aware(run, criteria_ok)

        # 3. signal_match
        signal_score, signal_notes, signal_detail = self._score_signal_match(
            task, run, trajectory
        )
        notes.extend(signal_notes)
        detail_metrics["signal_match_detail"] = signal_detail

        # 4. artifact_match
        artifact_score, artifact_notes, artifact_detail = self._score_artifact_match(
            task, artifacts
        )
        notes.extend(artifact_notes)
        detail_metrics["artifact_match_detail"] = artifact_detail

        # 5. tool_efficiency（复用旧逻辑）
        tool_efficiency = self._score_tool_efficiency(run)

        # 6. trajectory_quality（复用旧逻辑）
        trajectory_quality = self._score_trajectory_quality(run)

        scores: Dict[str, Optional[float]] = {
            "task_success": task_success,
            "signal_match": signal_score,
            "artifact_match": artifact_score,
            "tool_efficiency": tool_efficiency,
            "trajectory_quality": trajectory_quality,
        }

        # 7. weighted_score
        weights = task.get("scoring_weights", {})
        weighted = self._compute_weighted_score(scores, weights)
        detail_metrics["weighted_score"] = weighted

        detail_metrics["duration_ms"] = run.duration_ms
        detail_metrics["iterations"] = run.iterations
        detail_metrics["tool_calls"] = run.tool_calls
        detail_metrics["tool_errors"] = run.tool_errors
        detail_metrics["files_generated"] = len(artifacts)

        return EvalRecord(
            run_id=run.run_id,
            task_id=task_id,
            variant_id=run.variant_id,
            status=run.status,
            metrics=detail_metrics,
            scores=scores,
            notes=notes,
        )

    # ── 内部评分辅助 ─────────────────────────────────────────

    def _score_task_success_aware(
        self, run: RunRecord, criteria_ok: bool
    ) -> float:
        """task_success = run 基础成功 AND pass_criteria 全部通过"""
        if run.status != "passed":
            return 0.0
        return 1.0 if criteria_ok else 0.0

    def _evaluate_pass_criteria(
        self, task: dict, run: RunRecord, final_response_present: bool
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        逐项检查 pass_criteria，返回 (全部通过, 失败说明列表, 逐项结果 dict)。
        """
        pc = task.get("pass_criteria", {})
        results: Dict[str, Any] = {}
        failures: List[str] = []
        all_ok = True

        if "final_response_non_empty" in pc:
            ok = not pc["final_response_non_empty"] or final_response_present
            results["final_response_non_empty"] = ok
            if not ok:
                all_ok = False
                failures.append("pass_criteria 失败: final_response_non_empty — 最终回答为空")

        if "tool_errors_max" in pc:
            limit = pc["tool_errors_max"]
            ok = run.tool_errors <= limit
            results["tool_errors_max"] = {"limit": limit, "actual": run.tool_errors, "ok": ok}
            if not ok:
                all_ok = False
                failures.append(
                    f"pass_criteria 失败: tool_errors_max — 允许 {limit}，实际 {run.tool_errors}"
                )

        if "iterations_max" in pc:
            limit = pc["iterations_max"]
            ok = run.iterations <= limit
            results["iterations_max"] = {"limit": limit, "actual": run.iterations, "ok": ok}
            if not ok:
                all_ok = False
                failures.append(
                    f"pass_criteria 失败: iterations_max — 允许 {limit}，实际 {run.iterations}"
                )

        return all_ok, failures, results

    def _score_signal_match(
        self, task: dict, run: RunRecord, trajectory: List[dict]
    ) -> Tuple[float, List[str], Dict[str, Any]]:
        """
        expected_signals 命中率 + forbidden_signals 扣分。

        支持语法：
          skill:<name>
          tool:<ToolName>
          tool:<ToolName>:<path_contains>
          client_tool:<name>
          client_tool:<a>|<b>
        """
        expected, waived = self._get_effective_expected_signals(task, run)
        forbidden: List[str] = task.get("forbidden_signals", [])

        hits: List[str] = []
        misses: List[str] = []

        for sig in expected:
            if self._check_signal(sig, trajectory):
                hits.append(sig)
            else:
                misses.append(sig)

        forbidden_hits: List[str] = []
        for sig in forbidden:
            if self._check_signal(sig, trajectory):
                forbidden_hits.append(sig)

        notes: List[str] = []
        if misses:
            notes.append(f"signal 缺失: {', '.join(misses)}")
        if forbidden_hits:
            notes.append(f"forbidden signal 命中: {', '.join(forbidden_hits)}")
        if waived:
            notes.append(f"signal 豁免({run.variant_id}): {', '.join(waived)}")

        if not expected and not forbidden:
            score = 1.0
        elif not expected:
            score = 0.0 if forbidden_hits else 1.0
        else:
            hit_ratio = len(hits) / len(expected)
            penalty = 0.2 * len(forbidden_hits) if forbidden_hits else 0.0
            score = round(max(0.0, hit_ratio - penalty), 2)

        detail = {
            "expected": expected,
            "waived_expected": waived,
            "hits": hits,
            "misses": misses,
            "forbidden": forbidden,
            "forbidden_hits": forbidden_hits,
        }
        return score, notes, detail

    def _get_effective_expected_signals(
        self, task: dict, run: RunRecord
    ) -> Tuple[List[str], List[str]]:
        expected: List[str] = task.get("expected_signals", [])
        if run.variant_id != "no_skill":
            return expected, []

        effective: List[str] = []
        waived: List[str] = []
        for signal in expected:
            if self._is_skill_dependent_signal(signal):
                waived.append(signal)
            else:
                effective.append(signal)
        return effective, waived

    def _is_skill_dependent_signal(self, signal: str) -> bool:
        if signal.startswith("skill:"):
            return True

        if not signal.startswith("tool:"):
            return False

        parts = signal[len("tool:"):].split(":", 1)
        if len(parts) != 2:
            return False

        normalized_path = self._normalize_workspace_path(parts[1])
        return normalized_path.startswith("/workspace/skills/")

    def _check_signal(self, signal: str, trajectory: List[dict]) -> bool:
        """检查单条 signal 是否在 trajectory 中命中"""
        if signal.startswith("skill:"):
            target = signal[len("skill:"):]
            return any(
                evt.get("type") == "skill_injected"
                and target in (evt.get("skills") or [])
                for evt in trajectory
            )

        if signal.startswith("client_tool:"):
            spec = signal[len("client_tool:"):]
            alternatives = [s.strip() for s in spec.split("|")]
            return any(
                evt.get("type") == "client_tool_emitted"
                and evt.get("tool_name") in alternatives
                for evt in trajectory
            )

        if signal.startswith("tool:"):
            parts = signal[len("tool:"):].split(":", 1)
            tool_name = parts[0]
            path_contains = parts[1] if len(parts) > 1 else None
            normalized_path_contains = (
                self._normalize_workspace_path(path_contains)
                if path_contains is not None
                else None
            )

            for evt in trajectory:
                if evt.get("type") not in ("tool_call_started", "tool_call_finished"):
                    continue
                if evt.get("tool_name") != tool_name:
                    continue
                if path_contains is None:
                    return True
                args = evt.get("arguments") or {}
                raw_path = args.get("path")
                if isinstance(raw_path, str):
                    normalized_path = self._normalize_workspace_path(raw_path)
                    if (
                        path_contains in raw_path
                        or normalized_path_contains in normalized_path
                    ):
                        return True
                args_str = str(args)
                if (
                    path_contains in args_str
                    or normalized_path_contains in args_str
                ):
                    return True

            return False

        return False

    def _score_artifact_match(
        self, task: dict, artifacts: List[str]
    ) -> Tuple[float, List[str], Dict[str, Any]]:
        """
        expected_artifacts glob 匹配。
        每个 pattern 至少有一个 artifact 命中即算匹配。
        """
        patterns: List[str] = task.get("expected_artifacts", [])
        if not patterns:
            return 1.0, [], {"patterns": [], "matched": [], "missing": []}

        matched: List[str] = []
        missing: List[str] = []
        normalized_artifacts = [self._normalize_workspace_path(art) for art in artifacts]

        for pattern in patterns:
            normalized_pattern = self._normalize_workspace_pattern(pattern)
            found = any(
                fnmatch.fnmatch(art, normalized_pattern) for art in normalized_artifacts
            )
            if found:
                matched.append(pattern)
            else:
                missing.append(pattern)

        notes: List[str] = []
        if missing:
            notes.append(f"artifact 缺失: {', '.join(missing)}")

        score = round(len(matched) / len(patterns), 2)
        detail = {"patterns": patterns, "matched": matched, "missing": missing}
        return score, notes, detail

    @staticmethod
    def _compute_weighted_score(
        scores: Dict[str, Optional[float]], weights: Dict[str, float]
    ) -> float:
        """
        根据 scoring_weights 计算加权总分。
        只对 weights 中列出且 scores 里非 None 的项加权。
        """
        total_weight = 0.0
        weighted_sum = 0.0

        for key, w in weights.items():
            val = scores.get(key)
            if val is not None:
                weighted_sum += val * w
                total_weight += w

        if total_weight == 0.0:
            return 0.0
        return round(weighted_sum / total_weight, 4)

    # ── Phase 1 共用评分子项 ─────────────────────────────────

    def _score_task_success(self, run: RunRecord) -> int:
        if run.status == "passed":
            return 1
        return 0

    def _score_tool_efficiency(self, run: RunRecord) -> float:
        if run.tool_calls == 0:
            return 1.0
        base = 1.0
        base -= 0.15 * run.tool_errors
        extra = max(0, run.tool_calls - run.iterations * 3)
        base -= 0.05 * extra
        return round(max(0.0, min(1.0, base)), 2)

    def _score_artifact_completeness(self, run: RunRecord, artifacts: List[str]) -> Optional[float]:
        if run.task_id == "adhoc":
            if len(artifacts) > 0:
                return 1.0
            return None
        return 1.0 if len(artifacts) > 0 else 0.0

    def _score_trajectory_quality(self, run: RunRecord) -> float:
        score = 1.0
        if run.status != "passed":
            score -= 0.3
        if run.tool_errors > 0:
            score -= min(0.3, 0.1 * run.tool_errors)
        if run.iterations > 15:
            score -= 0.2
        elif run.iterations > 10:
            score -= 0.1
        return round(max(0.0, min(1.0, score)), 2)
