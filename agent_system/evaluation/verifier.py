"""
Result-first verifier

面向最终结果而非 trajectory，对 task 里预埋的 verifier 规则执行首版校验。
支持 target: final_response_json (含模糊提取) / script_stdout (从 trajectory 提取)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import RunRecord


class ResultVerifier:
    """执行 task.verifier 定义的结果校验。"""

    def verify(
        self,
        task: dict,
        run: RunRecord,
        artifacts: list[str],
        final_response_text: str,
        final_response_present: bool,
        session_id: str | None,
        run_dir: str | Path | None,
        trajectory: list[dict] | None = None,
    ) -> dict[str, Any]:
        self._current_task = task
        verifier = task.get("verifier")
        if not isinstance(verifier, dict) or not verifier:
            return {
                "configured": False,
                "mode": None,
                "target": None,
                "score": None,
                "passed": None,
                "checks": [],
                "summary": {
                    "total_checks": 0,
                    "passed_checks": 0,
                    "failed_checks": 0,
                },
                "context": self._build_context(
                    task=task,
                    run=run,
                    artifacts=artifacts,
                    final_response_text=final_response_text,
                    final_response_present=final_response_present,
                    session_id=session_id,
                    run_dir=run_dir,
                    trajectory=trajectory,
                ),
            }

        context = self._build_context(
            task=task,
            run=run,
            artifacts=artifacts,
            final_response_text=final_response_text,
            final_response_present=final_response_present,
            session_id=session_id,
            run_dir=run_dir,
            trajectory=trajectory,
        )
        target = verifier.get("target")
        mode = verifier.get("mode")

        try:
            target_value, target_detail = self._resolve_target_value(verifier, context)
        except ValueError as exc:
            return {
                "configured": True,
                "mode": mode,
                "target": target,
                "score": 0.0,
                "passed": False,
                "checks": [],
                "summary": {
                    "total_checks": 0,
                    "passed_checks": 0,
                    "failed_checks": 0,
                },
                "failure_reason": str(exc),
                "target_detail": target_detail_from_error(target, context),
            }

        checks = verifier.get("checks", [])
        if not isinstance(checks, list):
            raise ValueError("verifier.checks 必须是 list")

        executed_checks: list[dict[str, Any]] = []
        passed_checks = 0
        failed_checks = 0
        weighted_total = 0.0
        weighted_passed = 0.0
        unweighted_total = 0
        unweighted_passed = 0

        for index, check in enumerate(checks):
            if not isinstance(check, dict):
                raise ValueError(f"verifier.checks[{index}] 必须是 object")

            result = self._run_check(target_value, check)
            executed_checks.append(result)

            weight = result["weight"]
            if weight is None:
                unweighted_total += 1
                if result["passed"]:
                    unweighted_passed += 1
            else:
                weighted_total += weight
                if result["passed"]:
                    weighted_passed += weight

            if result["passed"]:
                passed_checks += 1
            else:
                failed_checks += 1

        score = self._compute_score(
            weighted_total=weighted_total,
            weighted_passed=weighted_passed,
            unweighted_total=unweighted_total,
            unweighted_passed=unweighted_passed,
        )
        passed = failed_checks == 0

        return {
            "configured": True,
            "mode": mode,
            "target": target,
            "score": score,
            "passed": passed,
            "checks": executed_checks,
            "summary": {
                "total_checks": len(executed_checks),
                "passed_checks": passed_checks,
                "failed_checks": failed_checks,
            },
            "target_detail": target_detail,
        }

    def _build_context(
        self,
        task: dict,
        run: RunRecord,
        artifacts: list[str],
        final_response_text: str,
        final_response_present: bool,
        session_id: str | None,
        run_dir: str | Path | None,
        trajectory: list[dict] | None = None,
    ) -> dict[str, Any]:
        return {
            "task": task,
            "run": run.to_dict(),
            "artifacts": artifacts,
            "final_response_text": final_response_text,
            "final_response_present": final_response_present,
            "session_id": session_id,
            "run_dir": str(run_dir) if run_dir is not None else None,
            "trajectory": trajectory or [],
        }

    def _resolve_target_value(
        self,
        verifier: dict,
        context: dict[str, Any],
    ) -> tuple[Any, dict[str, Any]]:
        target = verifier.get("target")
        if target == "final_response_json":
            return self._parse_json_response(context["final_response_text"])
        if target == "script_stdout":
            return self._parse_script_stdout(context.get("trajectory", []))
        raise ValueError(f"暂不支持的 verifier.target: {target!r}")

    # ── JSON 解析 ──────────────────────────────────────────────

    def _parse_json_response(self, text: str) -> tuple[Any, dict[str, Any]]:
        """从 response 中提取 JSON，支持三级 fallback：
        1. 纯 JSON（json.loads）
        2. markdown code fence 中的 JSON
        3. 文本中最后一个 {...} 块
        """
        if not isinstance(text, str) or not text.strip():
            raise ValueError("final_response_text 为空，无法解析为 JSON 输出")

        stripped = text.strip()

        # 1) 纯 JSON
        try:
            parsed = json.loads(stripped)
            return parsed, {
                "parser": "json.loads",
                "raw_length": len(text),
                "parsed_type": type(parsed).__name__,
            }
        except json.JSONDecodeError:
            pass

        # 2) markdown code fence: ```json ... ``` 或 ``` ... ```
        fence_pattern = re.compile(
            r"```(?:json)?\s*\n(.*?)```", re.DOTALL
        )
        for m in reversed(list(fence_pattern.finditer(stripped))):
            try:
                parsed = json.loads(m.group(1).strip())
                return parsed, {
                    "parser": "code_fence",
                    "raw_length": len(text),
                    "parsed_type": type(parsed).__name__,
                }
            except json.JSONDecodeError:
                continue

        # 3) 最后一个 {...} 块
        brace_pattern = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}")
        matches = list(brace_pattern.finditer(stripped))
        for m in reversed(matches):
            try:
                parsed = json.loads(m.group(0))
                return parsed, {
                    "parser": "brace_extract",
                    "raw_length": len(text),
                    "parsed_type": type(parsed).__name__,
                }
            except json.JSONDecodeError:
                continue

        raise ValueError(
            "final_response_text 中未找到可解析的 JSON 内容"
        )

    # ── script_stdout 提取 ─────────────────────────────────────

    def _parse_script_stdout(self, trajectory: list[dict]) -> tuple[Any, dict[str, Any]]:
        """从 trajectory 中提取成功 Bash 执行的 stdout，合并所有 JSON dict 输出。

        agent 可能分段执行多个 Bash（如 A+B 在一个脚本、C 在另一个脚本），
        策略：
        1. 收集所有成功 Bash 的 stdout（按时间正序，即 reversed(trajectory) 再 reverse）
        2. 解析每个输出为 JSON；dict 类型的输出逐层 merge（越晚越优先）
        3. 如果 merge 结果非空，返回合并后的 dict
        4. 如果没有 dict 输出，fallback 到最后一个可解析的 JSON（list/number 等）
        5. 全部无法解析时抛出 ValueError
        """
        bash_outputs: list[str] = []
        for event in reversed(trajectory):
            if (
                event.get("type") == "tool_call_finished"
                and event.get("tool_name") == "Bash"
                and event.get("status") == "success"
                and event.get("message")
            ):
                bash_outputs.append(event["message"])

        if not bash_outputs:
            raise ValueError(
                "trajectory 中未找到成功的 Bash 执行输出"
                "（script_stdout target 需要 Bash 工具产生 stdout）"
            )

        # bash_outputs 目前是"逆序"（最新的在前），还原为时间正序再处理
        bash_outputs_chrono = list(reversed(bash_outputs))

        merged: dict = {}
        non_dict_fallback: tuple[Any, dict] | None = None
        dict_sources: list[int] = []
        last_error = None

        for idx, output in enumerate(bash_outputs_chrono):
            try:
                parsed, detail = self._parse_json_response(output)
            except ValueError as exc:
                last_error = exc
                continue

            if isinstance(parsed, dict):
                merged.update(parsed)
                dict_sources.append(idx)
            else:
                non_dict_fallback = (parsed, detail)

        if merged:
            return merged, {
                "parser": "script_stdout_merge",
                "bash_candidates": len(bash_outputs_chrono),
                "merged_from_indices": dict_sources,
            }

        if non_dict_fallback is not None:
            parsed, detail = non_dict_fallback
            detail["bash_candidates"] = len(bash_outputs_chrono)
            return parsed, detail

        raise ValueError(
            f"trajectory 中 {len(bash_outputs_chrono)} 个 Bash 输出均无法解析为 JSON: {last_error}"
        )

    def _run_check(self, target_value: Any, check: dict[str, Any]) -> dict[str, Any]:
        check_id = check.get("id") or check.get("path") or "unnamed_check"
        check_type = check.get("type")
        path = check.get("path", "")
        expected, expected_source = self._resolve_expected_value(check)
        weight = check.get("weight")

        found, actual = _get_value_at_path(target_value, path)
        if not found:
            return {
                "id": check_id,
                "type": check_type,
                "path": path,
                "expected": expected,
                "actual": None,
                "passed": False,
                "weight": weight,
                "expected_source": expected_source,
                "message": f"path 未找到: {path}",
            }

        if check_type == "exact_match":
            passed = actual == expected
            message = "exact_match 通过" if passed else "exact_match 不匹配"
        elif check_type == "numeric_tolerance":
            tolerance = check.get("tolerance")
            tolerance_mode = check.get("tolerance_mode", "absolute")
            passed, message = self._check_numeric_tolerance(
                actual, expected, tolerance, tolerance_mode,
            )
        elif check_type == "json_subset":
            passed = _is_json_subset(actual, expected)
            message = "json_subset 通过" if passed else "json_subset 不匹配"
        else:
            raise ValueError(f"不支持的 verifier check 类型: {check_type}")

        return {
            "id": check_id,
            "type": check_type,
            "path": path,
            "expected": expected,
            "actual": actual,
            "passed": passed,
            "weight": weight,
            "expected_source": expected_source,
            "message": message,
        }

    def _resolve_expected_value(self, check: dict[str, Any]) -> tuple[Any, str]:
        if "expected" in check:
            return check.get("expected"), "check.expected"

        expected_from = check.get("expected_from")
        if isinstance(expected_from, str) and expected_from.strip():
            expected_path = _normalize_ground_truth_path(expected_from)
            found, expected = _get_value_at_path(self._current_task, expected_path)
            if not found:
                raise ValueError(f"expected_from 未找到: {expected_from}")
            return expected, f"task.{expected_path}"

        path = check.get("path", "")
        if isinstance(path, str) and path:
            expected_path = f"ground_truth.{path}"
            found, expected = _get_value_at_path(self._current_task, expected_path)
            if found:
                return expected, f"task.{expected_path}"

        raise ValueError(
            f"check '{check.get('id') or path or 'unnamed_check'}' 缺少 expected，"
            "且无法从 ground_truth 自动解析"
        )

    @staticmethod
    def _check_numeric_tolerance(
        actual: Any,
        expected: Any,
        tolerance: Any,
        tolerance_mode: str = "absolute",
    ) -> tuple[bool, str]:
        if isinstance(actual, bool) or isinstance(expected, bool):
            return False, "numeric_tolerance 要求 actual/expected 都是数值，不能是 bool"
        if not isinstance(actual, (int, float)) or not isinstance(expected, (int, float)):
            return False, "numeric_tolerance 要求 actual/expected 都是数值"
        if not isinstance(tolerance, (int, float)):
            return False, "numeric_tolerance 缺少合法 tolerance"

        a, e, t = float(actual), float(expected), float(tolerance)
        diff = abs(a - e)

        if tolerance_mode == "relative":
            # 相对容差: |actual - expected| / |expected| <= tolerance
            # expected == 0 时退化为绝对容差
            if e == 0.0:
                passed = diff <= t
                mode_label = "relative(fallback_abs, expected=0)"
            else:
                rel_diff = diff / abs(e)
                passed = rel_diff <= t
                if passed:
                    return True, f"numeric_tolerance(relative) 通过，相对差 {rel_diff:.6f}"
                return False, (
                    f"numeric_tolerance(relative) 不匹配，"
                    f"相对差 {rel_diff:.6f} > tolerance {t:.6f}"
                )
        else:
            mode_label = "absolute"

        passed = diff <= t
        if passed:
            return True, f"numeric_tolerance({mode_label}) 通过，差值 {diff:.6f}"
        return False, (
            f"numeric_tolerance({mode_label}) 不匹配，"
            f"差值 {diff:.6f} > tolerance {t:.6f}"
        )

    @staticmethod
    def _compute_score(
        weighted_total: float,
        weighted_passed: float,
        unweighted_total: int,
        unweighted_passed: int,
    ) -> float:
        if weighted_total > 0:
            return round(weighted_passed / weighted_total, 4)
        if unweighted_total > 0:
            return round(unweighted_passed / unweighted_total, 4)
        return 0.0


def _get_value_at_path(data: Any, path: str) -> tuple[bool, Any]:
    if not path:
        return True, data

    current = data
    for part in str(path).split("."):
        if isinstance(current, dict):
            if part not in current:
                return False, None
            current = current[part]
            continue

        if isinstance(current, list):
            try:
                index = int(part)
            except (TypeError, ValueError):
                return False, None
            if index < 0 or index >= len(current):
                return False, None
            current = current[index]
            continue

        return False, None

    return True, current


def _normalize_ground_truth_path(path: str) -> str:
    normalized = str(path).strip()
    if normalized.startswith("task."):
        normalized = normalized[len("task."):]
    if normalized.startswith("ground_truth."):
        return normalized
    return f"ground_truth.{normalized}"


def _is_json_subset(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        for key, expected_value in expected.items():
            if key not in actual:
                return False
            if not _is_json_subset(actual[key], expected_value):
                return False
        return True

    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) < len(expected):
            return False
        return all(_is_json_subset(a, e) for a, e in zip(actual, expected))

    return actual == expected


def target_detail_from_error(target: Any, context: dict[str, Any]) -> dict[str, Any]:
    return {
        "target": target,
        "final_response_present": context.get("final_response_present"),
        "raw_length": len(context.get("final_response_text") or ""),
    }
