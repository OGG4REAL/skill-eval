"""
BenchmarkRunner — 最小 benchmark 执行器

跑通「单 task → 多 variant → 多 trial → benchmark JSON」闭环。

执行流程：
  TaskLoader.get_task()
    → VariantManager.resolve_variant()
    → _prepare_upload_fixtures()
    → setup_system(session_id=..., allowed_skills=..., variant_context=...)
    → agent.run(user_query)
    → _load_run_outputs()
    → RuleScorer.score_task_run()
    → _aggregate_cases()
    → _write_benchmark_result()
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import Config
from ..session import sanitize_session_id
from .task_loader import TaskLoader
from .variant_manager import VariantManager, VariantResolutionError
from .scorer import RuleScorer
from .models import RunRecord


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _generate_benchmark_id() -> str:
    import secrets
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = secrets.token_hex(3)
    return f"bench_{ts}_{suffix}"


def _sanitize(s: str) -> str:
    """文件系统安全化：只保留字母数字和连字符"""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", s).strip("-") or "x"


class BenchmarkRunner:
    """最小可运行的 benchmark 执行器"""

    def __init__(self, workspace_root: Path | None = None):
        self._workspace = (workspace_root or Config.WORKSPACE_ROOT).resolve()
        self._tasks_dir = self._workspace / "evaluations" / "tasks"
        self._fixtures_dir = self._workspace / "evaluations" / "fixtures"
        self._output_dir = self._workspace / "evaluations" / "benchmarks" / "runs"
        self._sessions_root = self._workspace / "sessions"
        self._skills_dir = self._workspace / "skills"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._sessions_root.mkdir(parents=True, exist_ok=True)

        self._task_loader = TaskLoader(self._tasks_dir)
        self._variant_manager = VariantManager()
        self._scorer = RuleScorer()

    # ── 公开接口 ─────────────────────────────────────────────

    def run_task(
        self,
        task_id: str,
        variants: list[str] | None = None,
        trials: int = 1,
    ) -> dict:
        task = self._task_loader.get_task(task_id)
        variant_ids = variants or list(task["variants"])
        return self._execute(
            tasks=[task],
            variant_ids=variant_ids,
            trials=trials,
            scope={"task_id": task_id, "group": None, "all": False},
        )

    def run_group(
        self,
        group: str,
        variants: list[str] | None = None,
        trials: int = 1,
    ) -> dict:
        tasks = self._task_loader.list_group(group)
        if not tasks:
            raise ValueError(f"group '{group}' 没有匹配的 task")
        return self._execute(
            tasks=tasks,
            variant_ids=variants,
            trials=trials,
            scope={"task_id": None, "group": group, "all": False},
        )

    def run_all(self, trials: int = 1) -> dict:
        tasks = self._task_loader.list_tasks()
        return self._execute(
            tasks=tasks,
            variant_ids=None,
            trials=trials,
            scope={"task_id": None, "group": None, "all": True},
        )

    # ── 核心编排 ─────────────────────────────────────────────

    def _execute(
        self,
        tasks: list[dict],
        variant_ids: list[str] | None,
        trials: int,
        scope: dict,
    ) -> dict:
        benchmark_id = _generate_benchmark_id()
        started_at = _now_iso()
        cases: list[dict] = []

        for task in tasks:
            task_variants = variant_ids or list(task["variants"])
            for variant_id in task_variants:
                for trial_idx in range(1, trials + 1):
                    case = self._run_single_case(
                        task, variant_id, trial_idx, benchmark_id
                    )
                    cases.append(case)

        finished_at = _now_iso()
        succeeded = sum(1 for c in cases if c["status"] == "passed")

        all_variants = (
            variant_ids
            if variant_ids is not None
            else sorted(set(v for t in tasks for v in t["variants"]))
        )
        scope_out = {
            **scope,
            "variants": all_variants,
            "trials": trials,
        }

        result = {
            "benchmark_id": benchmark_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "scope": scope_out,
            "summary": {
                "cases_total": len(cases),
                "cases_succeeded": succeeded,
                "cases_failed": len(cases) - succeeded,
            },
            "cases": cases,
            "aggregates": self._aggregate_cases(cases),
        }

        path = self._write_benchmark_result(result, benchmark_id, scope)
        print(f"\n[Benchmark] 结果已写入: {path}")
        return result

    # ── 单 case 执行 ─────────────────────────────────────────

    def _run_single_case(
        self, task: dict, variant_id: str, trial_index: int, benchmark_id: str
    ) -> dict:
        task_id = task["task_id"]
        session_id = self._build_session_id(benchmark_id, task_id, variant_id, trial_index)

        case: dict[str, Any] = {
            "task_id": task_id,
            "variant_id": variant_id,
            "trial_index": trial_index,
            "session_id": session_id,
            "run_id": None,
            "status": "failed",
            "run_status": None,
            "error": None,
            "variant": None,
            "duration_ms": None,
            "tool_calls": None,
            "tool_errors": None,
            "score": None,
        }
        case_skills_dir: Path | None = None

        # 1. resolve variant
        try:
            resolved = self._variant_manager.resolve_variant(task, variant_id)
            allowed_skills = self._variant_manager.get_allowed_skills(resolved)
            case["variant"] = {
                "enabled_skills": resolved["enabled_skills"],
                "pre_injected_skills": resolved.get("pre_injected_skills", []),
                "skill_version_map": resolved.get("skill_version_map", {}),
                "routing_enabled": resolved["routing_enabled"],
            }
        except VariantResolutionError as e:
            case["error"] = f"variant resolve 失败: {e}"
            return case

        # 2. fixture 准备
        try:
            self._prepare_upload_fixtures(task, session_id)
            self._check_unsupported_setup(task)
            case_skills_dir = self._prepare_case_skills_dir(session_id, allowed_skills)
        except Exception as e:
            case["error"] = f"fixture 准备失败: {e}"
            if case_skills_dir and case_skills_dir.exists():
                shutil.rmtree(case_skills_dir, ignore_errors=True)
            return case

        # 3. 执行 agent
        agent = None
        response_text = ""
        run_id = None
        try:
            from ..main import setup_system
            agent = setup_system(
                session_id=session_id,
                allowed_skills=allowed_skills,
                variant_context=resolved,
                sessions_root=self._sessions_root,
                skills_dir=case_skills_dir,
            )
            result = agent.run(task["input"]["user_query"])
            response_text = result.get("response", "")
            run_id = result.get("run_id")
            case["run_id"] = run_id
        except Exception as e:
            case["error"] = f"agent 执行失败: {e}"
        finally:
            self._cleanup_agent(agent)

        if not run_id:
            if case_skills_dir and case_skills_dir.exists():
                shutil.rmtree(case_skills_dir, ignore_errors=True)
            return case

        # 4. 读取 run 产出并重新评分
        try:
            run_record, trajectory, artifacts = self._load_run_outputs(session_id, run_id)
            final_present = bool(response_text and response_text.strip())
            eval_record = self._scorer.score_task_run(
                task=task,
                run=run_record,
                trajectory=trajectory,
                artifacts=artifacts,
                final_response_present=final_present,
            )
            case["run_status"] = run_record.status
            task_success = eval_record.scores.get("task_success")
            case["status"] = "passed" if task_success == 1.0 else "failed"
            case["duration_ms"] = run_record.duration_ms
            case["tool_calls"] = run_record.tool_calls
            case["tool_errors"] = run_record.tool_errors
            case["score"] = {
                "weighted_score": eval_record.metrics.get("weighted_score"),
                "scores": eval_record.scores,
                "notes": eval_record.notes,
            }
        except Exception as e:
            case["error"] = (case.get("error") or "") + f" | 评分失败: {e}"
        finally:
            if case_skills_dir and case_skills_dir.exists():
                shutil.rmtree(case_skills_dir, ignore_errors=True)

        return case

    # ── 辅助方法 ─────────────────────────────────────────────

    @staticmethod
    def _build_session_id(
        benchmark_id: str, task_id: str, variant_id: str, trial_index: int
    ) -> str:
        raw = f"{benchmark_id}__{task_id}__{variant_id}__t{trial_index}"
        return sanitize_session_id(raw)

    def _prepare_upload_fixtures(self, task: dict, session_id: str) -> list[str]:
        """复制 uploads fixture 到 session uploads/ 目录"""
        from ..session import ensure_session_dirs

        _, uploads_dir, _, _ = ensure_session_dirs(session_id, sessions_root=self._sessions_root)
        uploads = task.get("input", {}).get("session_setup", {}).get("uploads", [])
        copied: list[str] = []

        for rel_path in uploads:
            src = self._fixtures_dir / rel_path
            if not src.exists():
                raise FileNotFoundError(f"fixture 不存在: {src}")
            dst = uploads_dir / Path(rel_path).name
            shutil.copy2(str(src), str(dst))
            copied.append(str(dst))

        return copied

    def _prepare_case_skills_dir(self, session_id: str, allowed_skills: list[str]) -> Path:
        """
        为单个 benchmark case 生成隔离的 skills 视图。

        no_skill 会得到空目录；其它 variant 只复制 allowlist 中的技能。
        """
        case_skills_dir = self._workspace / ".benchmark-skills" / session_id
        if case_skills_dir.exists():
            shutil.rmtree(case_skills_dir)
        case_skills_dir.mkdir(parents=True, exist_ok=True)

        for skill_name in allowed_skills:
            src = self._skills_dir / skill_name
            if not src.exists():
                raise FileNotFoundError(f"skill 不存在: {src}")
            shutil.copytree(src, case_skills_dir / skill_name)

        return case_skills_dir

    @staticmethod
    def _check_unsupported_setup(task: dict) -> None:
        setup = task.get("input", {}).get("session_setup", {})
        if setup.get("workspace_files"):
            raise NotImplementedError(
                "当前 runner 尚未实现 workspace_files 准备能力，"
                f"task '{task.get('task_id')}' 声明了 workspace_files: {setup['workspace_files']}"
            )
        if setup.get("history_seed"):
            raise NotImplementedError(
                "当前 runner 尚未实现 history_seed 准备能力，"
                f"task '{task.get('task_id')}' 声明了 history_seed"
            )

    def _load_run_outputs(
        self, session_id: str, run_id: str
    ) -> tuple[RunRecord, list[dict], list[str]]:
        """从磁盘读取 run.json / trajectory.jsonl / artifacts.json"""
        run_dir = self._sessions_root / session_id / "runs" / run_id

        run_path = run_dir / "run.json"
        if not run_path.exists():
            raise FileNotFoundError(f"run.json 不存在: {run_path}")
        raw = json.loads(run_path.read_text(encoding="utf-8"))
        run_record = RunRecord(
            run_id=raw.get("run_id", run_id),
            session_id=raw.get("session_id", session_id),
            task_id=raw.get("task_id", "adhoc"),
            variant_id=raw.get("variant_id", "baseline"),
            status=raw.get("status", "failed"),
            iterations=raw.get("iterations", 0),
            tool_calls=raw.get("tool_calls", 0),
            tool_errors=raw.get("tool_errors", 0),
            duration_ms=raw.get("duration_ms"),
            skills=raw.get("skills", []),
            user_input=raw.get("user_input", ""),
            enabled_skills=raw.get("enabled_skills", []),
            skill_version_map=raw.get("skill_version_map", {}),
            routing_enabled=raw.get("routing_enabled"),
        )

        traj_path = run_dir / "trajectory.jsonl"
        if not traj_path.exists():
            raise FileNotFoundError(f"trajectory.jsonl 不存在: {traj_path}")
        trajectory: list[dict] = []
        for line in traj_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    trajectory.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

        art_path = run_dir / "artifacts.json"
        if not art_path.exists():
            raise FileNotFoundError(f"artifacts.json 不存在: {art_path}")
        art_data = json.loads(art_path.read_text(encoding="utf-8"))
        artifacts: list[str] = art_data.get("files", [])

        return run_record, trajectory, artifacts

    @staticmethod
    def _cleanup_agent(agent: Any) -> None:
        if agent is None:
            return
        if hasattr(agent, "_mcp_client") and agent._mcp_client:
            try:
                agent._mcp_client.cleanup()
            except Exception:
                pass

    @staticmethod
    def _aggregate_cases(cases: list[dict]) -> dict:
        """按 (task_id, variant_id) 聚合统计"""
        groups: dict[tuple[str, str], list[dict]] = {}
        for c in cases:
            key = (c["task_id"], c["variant_id"])
            groups.setdefault(key, []).append(c)

        by_task_variant: list[dict] = []
        for (tid, vid), grp in sorted(groups.items()):
            total = len(grp)
            passed = sum(1 for c in grp if c["status"] == "passed")

            ws_values = [
                c["score"]["weighted_score"]
                for c in grp
                if c.get("score") and c["score"].get("weighted_score") is not None
            ]
            dur_values = [c["duration_ms"] for c in grp if c.get("duration_ms") is not None]
            tc_values = [c["tool_calls"] for c in grp if c.get("tool_calls") is not None]
            te_values = [c["tool_errors"] for c in grp if c.get("tool_errors") is not None]

            def _avg(vals: list) -> float | None:
                return round(sum(vals) / len(vals), 4) if vals else None

            by_task_variant.append({
                "task_id": tid,
                "variant_id": vid,
                "trials": total,
                "pass_rate": round(passed / total, 4) if total else 0,
                "avg_weighted_score": _avg(ws_values),
                "avg_duration_ms": _avg(dur_values),
                "avg_tool_calls": _avg(tc_values),
                "avg_tool_errors": _avg(te_values),
            })

        return {"by_task_variant": by_task_variant}

    def _write_benchmark_result(
        self, data: dict, benchmark_id: str, scope: dict
    ) -> Path:
        if scope.get("task_id"):
            scope_tag = scope["task_id"]
        elif scope.get("group"):
            scope_tag = scope["group"]
        else:
            scope_tag = "all"
        filename = f"{benchmark_id}_{_sanitize(scope_tag)}.json"
        path = self._output_dir / filename
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path


# ── CLI 入口 ────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Skills Eval Benchmark Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--task", help="运行单个 task（按 task_id）")
    group.add_argument("--group", help="运行一组 task（按 group 名）")
    group.add_argument("--all", action="store_true", help="运行全部 task")

    parser.add_argument(
        "--variant", action="append", dest="variants",
        help="指定 variant（可多次使用），不传则跑 task 声明的全部 variants",
    )
    parser.add_argument("--trials", type=int, default=1, help="每个 case 的 trial 次数（默认 1）")

    args = parser.parse_args()
    runner = BenchmarkRunner()

    if args.task:
        result = runner.run_task(args.task, variants=args.variants, trials=args.trials)
    elif args.group:
        result = runner.run_group(args.group, variants=args.variants, trials=args.trials)
    else:
        result = runner.run_all(trials=args.trials)

    summary = result["summary"]
    print(
        f"\n[Benchmark] 完成: {summary['cases_total']} cases, "
        f"{summary['cases_succeeded']} passed, "
        f"{summary['cases_failed']} failed"
    )


if __name__ == "__main__":
    main()
