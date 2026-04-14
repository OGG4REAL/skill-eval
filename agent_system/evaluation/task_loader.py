"""
TaskLoader — benchmark 侧唯一的 task 读取与校验入口

职责：
- 从 evaluations/tasks/*.json 加载全部 task
- 严格校验新 schema，不兼容旧 schema
- 任一 task 非法时直接抛错，不做静默跳过
- 支持按 task_id / group 查询
"""
from __future__ import annotations

import copy
import json
import ntpath
import posixpath
from pathlib import Path, PurePosixPath
from typing import Any


VALID_EVAL_TYPES = {"uplift", "routing"}

REQUIRED_TOP_LEVEL = {
    "task_id": str,
    "group": str,
    "eval_type": str,
    "description": str,
    "input": dict,
    "variants": list,
    "target_skills": list,
    "expected_signals": list,
    "expected_artifacts": list,
    "pass_criteria": dict,
    "scoring_weights": dict,
}

OPTIONAL_TOP_LEVEL = {
    "forbidden_signals": list,
    "routing_expectation": dict,
    "output_contract": dict,
    "ground_truth": dict,
    "verifier": dict,
}

OPTIONAL_DEFAULTS: dict[str, Any] = {
    "forbidden_signals": [],
    "routing_expectation": {},
}

REQUIRED_INPUT = {
    "user_query": str,
    "session_setup": dict,
}

SESSION_SETUP_DEFAULTS: dict[str, Any] = {
    "uploads": [],
    "workspace_files": [],
    "history_seed": [],
}

STR_LIST_FIELDS = [
    "variants", "target_skills", "expected_signals",
    "expected_artifacts",
]

OPTIONAL_STR_LIST_FIELDS = ["forbidden_signals"]


class TaskLoadError(Exception):
    """task 加载或校验失败时抛出"""


class TaskLoader:
    """benchmark 侧 task 读取入口"""

    def __init__(self, tasks_dir: Path):
        self._tasks_dir = tasks_dir
        self._tasks: list[dict] = []
        self._by_id: dict[str, dict] = {}
        self._load_all()

    def list_tasks(self) -> list[dict]:
        return list(self._tasks)

    def get_task(self, task_id: str) -> dict:
        if task_id not in self._by_id:
            available = ", ".join(sorted(self._by_id.keys())) or "(无)"
            raise TaskLoadError(
                f"task_id '{task_id}' 不存在。可用: {available}"
            )
        return self._by_id[task_id]

    def list_group(self, group: str) -> list[dict]:
        return [t for t in self._tasks if t["group"] == group]

    def validate_task(self, task: dict, source: str) -> None:
        self._validate(task, source)

    # ── 内部实现 ──────────────────────────────────────────

    def _load_all(self) -> None:
        if not self._tasks_dir.is_dir():
            raise TaskLoadError(
                f"tasks 目录不存在: {self._tasks_dir}"
            )

        json_files = sorted(self._tasks_dir.glob("*.json"))
        if not json_files:
            raise TaskLoadError(
                f"tasks 目录为空: {self._tasks_dir}"
            )

        seen_ids: set[str] = set()
        tasks: list[dict] = []

        for fp in json_files:
            source = str(fp)
            try:
                raw = fp.read_text(encoding="utf-8")
                task = json.loads(raw)
            except json.JSONDecodeError as e:
                raise TaskLoadError(f"[{source}] JSON 解析失败: {e}") from e

            if not isinstance(task, dict):
                raise TaskLoadError(f"[{source}] 顶层必须是 object，实际是 {type(task).__name__}")

            self._validate(task, source)

            tid = task["task_id"]
            if tid in seen_ids:
                raise TaskLoadError(f"[{source}] task_id '{tid}' 重复")
            seen_ids.add(tid)

            self._fill_defaults(task)
            tasks.append(task)

        self._tasks = tasks
        self._by_id = {t["task_id"]: t for t in tasks}

    def _validate(self, task: dict, source: str) -> None:
        for field, expected_type in REQUIRED_TOP_LEVEL.items():
            if field not in task:
                raise TaskLoadError(f"[{source}] 缺少必填字段: {field}")
            if not isinstance(task[field], expected_type):
                raise TaskLoadError(
                    f"[{source}] 字段 '{field}' 类型错误: "
                    f"期望 {expected_type.__name__}，实际 {type(task[field]).__name__}"
                )

        for field, expected_type in OPTIONAL_TOP_LEVEL.items():
            if field in task and not isinstance(task[field], expected_type):
                raise TaskLoadError(
                    f"[{source}] 可选字段 '{field}' 类型错误: "
                    f"期望 {expected_type.__name__}，实际 {type(task[field]).__name__}"
                )

        if task["eval_type"] not in VALID_EVAL_TYPES:
            raise TaskLoadError(
                f"[{source}] eval_type '{task['eval_type']}' 不合法，"
                f"仅接受: {', '.join(sorted(VALID_EVAL_TYPES))}"
            )

        if not task["variants"]:
            raise TaskLoadError(f"[{source}] variants 不能为空列表")

        if not task["target_skills"]:
            raise TaskLoadError(f"[{source}] target_skills 不能为空列表")

        for field in STR_LIST_FIELDS:
            for i, elem in enumerate(task[field]):
                if not isinstance(elem, str):
                    raise TaskLoadError(
                        f"[{source}] {field}[{i}] 必须是 str，实际 {type(elem).__name__}: {elem!r}"
                    )

        for field in OPTIONAL_STR_LIST_FIELDS:
            if field in task:
                for i, elem in enumerate(task[field]):
                    if not isinstance(elem, str):
                        raise TaskLoadError(
                            f"[{source}] {field}[{i}] 必须是 str，实际 {type(elem).__name__}: {elem!r}"
                        )

        inp = task["input"]
        for field, expected_type in REQUIRED_INPUT.items():
            if field not in inp:
                raise TaskLoadError(f"[{source}] input 缺少必填字段: {field}")
            if not isinstance(inp[field], expected_type):
                raise TaskLoadError(
                    f"[{source}] input.{field} 类型错误: "
                    f"期望 {expected_type.__name__}，实际 {type(inp[field]).__name__}"
                )

        setup = inp["session_setup"]
        uploads = setup.get("uploads", [])
        if not isinstance(uploads, list):
            raise TaskLoadError(f"[{source}] session_setup.uploads 必须是 list")
        for path_val in uploads:
            if not isinstance(path_val, str):
                raise TaskLoadError(f"[{source}] session_setup.uploads 中包含非字符串元素: {path_val!r}")
            _validate_fixture_path(path_val, "uploads", source)

        workspace_files = setup.get("workspace_files", [])
        if not isinstance(workspace_files, list):
            raise TaskLoadError(f"[{source}] session_setup.workspace_files 必须是 list")
        for path_val in workspace_files:
            if not isinstance(path_val, str):
                raise TaskLoadError(f"[{source}] session_setup.workspace_files 中包含非字符串元素: {path_val!r}")
            _validate_fixture_path(path_val, "workspace_files", source)

        history_seed = setup.get("history_seed", [])
        if not isinstance(history_seed, list):
            raise TaskLoadError(f"[{source}] session_setup.history_seed 必须是 list")

        pc = task["pass_criteria"]
        if "final_response_non_empty" in pc and not isinstance(pc["final_response_non_empty"], bool):
            raise TaskLoadError(f"[{source}] pass_criteria.final_response_non_empty 必须是 bool")
        if "tool_errors_max" in pc and not isinstance(pc["tool_errors_max"], int):
            raise TaskLoadError(f"[{source}] pass_criteria.tool_errors_max 必须是 int")
        if "iterations_max" in pc and not isinstance(pc["iterations_max"], int):
            raise TaskLoadError(f"[{source}] pass_criteria.iterations_max 必须是 int")

        sw = task["scoring_weights"]
        for key, val in sw.items():
            if not isinstance(val, (int, float)):
                raise TaskLoadError(
                    f"[{source}] scoring_weights.{key} 必须是数值，"
                    f"实际 {type(val).__name__}: {val!r}"
                )

        self._validate_verifier_ground_truth_link(task, source)

    @staticmethod
    def _fill_defaults(task: dict) -> None:
        for field, default in OPTIONAL_DEFAULTS.items():
            if field not in task:
                task[field] = copy.deepcopy(default)

        setup = task["input"]["session_setup"]
        for field, default in SESSION_SETUP_DEFAULTS.items():
            if field not in setup:
                setup[field] = copy.deepcopy(default)

    @staticmethod
    def _validate_verifier_ground_truth_link(task: dict, source: str) -> None:
        verifier = task.get("verifier")
        if verifier is None:
            return
        if not isinstance(verifier, dict):
            return

        checks = verifier.get("checks", [])
        if not isinstance(checks, list):
            raise TaskLoadError(f"[{source}] verifier.checks 必须是 list")

        ground_truth = task.get("ground_truth")
        for idx, check in enumerate(checks):
            if not isinstance(check, dict):
                raise TaskLoadError(f"[{source}] verifier.checks[{idx}] 必须是 object")

            if "expected_from" in check and not isinstance(check["expected_from"], str):
                raise TaskLoadError(f"[{source}] verifier.checks[{idx}].expected_from 必须是 str")

            if "expected" in check and "expected_from" in check:
                raise TaskLoadError(
                    f"[{source}] verifier.checks[{idx}] 不能同时声明 expected 和 expected_from"
                )

            _VALID_TOLERANCE_MODES = {"absolute", "relative"}
            if "tolerance_mode" in check:
                tm = check["tolerance_mode"]
                if not isinstance(tm, str) or tm not in _VALID_TOLERANCE_MODES:
                    raise TaskLoadError(
                        f"[{source}] verifier.checks[{idx}].tolerance_mode "
                        f"必须是 {_VALID_TOLERANCE_MODES} 之一，实际为 {tm!r}"
                    )

            if ground_truth is None:
                continue

            if not isinstance(ground_truth, dict):
                raise TaskLoadError(f"[{source}] ground_truth 必须是 object")

            expected_path = _resolve_ground_truth_path_for_check(check)
            if expected_path is None:
                continue

            found, expected_from_ground_truth = _get_value_at_path(task, expected_path)
            if not found:
                raise TaskLoadError(
                    f"[{source}] verifier.checks[{idx}] 无法从 {expected_path} 解析 expected"
                )

            if "expected" in check and check.get("expected") != expected_from_ground_truth:
                raise TaskLoadError(
                    f"[{source}] verifier.checks[{idx}] 的 expected 与 {expected_path} 不一致"
                )


def _is_absolute(path_str: str) -> bool:
    """跨平台判定是否是绝对路径"""
    return posixpath.isabs(path_str) or ntpath.isabs(path_str)


def _validate_fixture_path(path_str: str, field_name: str, source: str) -> None:
    """校验 fixture 相对路径：拒绝绝对路径和路径穿越"""
    if _is_absolute(path_str):
        raise TaskLoadError(
            f"[{source}] session_setup.{field_name} 路径必须是相对 evaluations/fixtures/ 的相对路径，"
            f"不能是绝对路径: {path_str!r}"
        )
    normalized = PurePosixPath(path_str.replace("\\", "/"))
    try:
        resolved_parts = normalized.resolve().parts if hasattr(normalized, "resolve") else None
    except Exception:
        resolved_parts = None
    # PurePosixPath 无 resolve()，手动规范化检查 '..' 分量
    parts = list(normalized.parts)
    depth = 0
    for part in parts:
        if part == "..":
            depth -= 1
        elif part != ".":
            depth += 1
        if depth < 0:
            raise TaskLoadError(
                f"[{source}] session_setup.{field_name} 路径包含穿越 (..): {path_str!r}，"
                f"必须位于 evaluations/fixtures/ 内"
            )


def _resolve_ground_truth_path_for_check(check: dict) -> str | None:
    if "expected" in check:
        path = check.get("expected_from") or check.get("path")
    else:
        path = check.get("expected_from") or check.get("path")

    if not isinstance(path, str) or not path.strip():
        return None

    normalized = path.strip()
    if normalized.startswith("task."):
        normalized = normalized[len("task."):]
    if normalized.startswith("ground_truth."):
        return normalized
    return f"ground_truth.{normalized}"


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
