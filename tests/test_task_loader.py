"""TaskLoader 单元测试"""
from __future__ import annotations

import json
import copy
import pytest
from pathlib import Path

from agent_system.evaluation.task_loader import TaskLoader, TaskLoadError


# ── 最小合法 task 夹具 ────────────────────────────────────

MINIMAL_VALID_TASK = {
    "task_id": "test_task_alpha",
    "group": "test_group",
    "eval_type": "uplift",
    "description": "用于单元测试的最小合法 task",
    "input": {
        "user_query": "帮我做个分析",
        "session_setup": {
            "uploads": ["csv/some_file.csv"],
            "workspace_files": [],
            "history_seed": [],
        },
    },
    "variants": ["no_skill", "with_skill"],
    "target_skills": ["csv-data-summarizer"],
    "expected_signals": ["tool:Bash"],
    "expected_artifacts": [],
    "pass_criteria": {
        "final_response_non_empty": True,
        "tool_errors_max": 0,
        "iterations_max": 12,
    },
    "scoring_weights": {
        "task_success": 0.40,
        "signal_match": 0.20,
    },
}


def _make_task(**overrides) -> dict:
    """深拷贝最小合法 task 并应用覆盖"""
    t = copy.deepcopy(MINIMAL_VALID_TASK)
    for key, val in overrides.items():
        if key.startswith("input."):
            sub_key = key[len("input."):]
            t["input"][sub_key] = val
        elif key.startswith("session_setup."):
            sub_key = key[len("session_setup."):]
            t["input"]["session_setup"][sub_key] = val
        elif key.startswith("pass_criteria."):
            sub_key = key[len("pass_criteria."):]
            t["pass_criteria"][sub_key] = val
        else:
            t[key] = val
    return t


def _write_task(tasks_dir: Path, task: dict, filename: str | None = None) -> None:
    tasks_dir.mkdir(parents=True, exist_ok=True)
    fname = filename or f"{task.get('task_id', 'unnamed')}.json"
    (tasks_dir / fname).write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 正向测试 ──────────────────────────────────────────────

class TestLoadValid:
    """合法 task 加载"""

    def test_load_single(self, tmp_path: Path):
        _write_task(tmp_path, MINIMAL_VALID_TASK)
        loader = TaskLoader(tmp_path)
        assert len(loader.list_tasks()) == 1

    def test_get_task_by_id(self, tmp_path: Path):
        _write_task(tmp_path, MINIMAL_VALID_TASK)
        loader = TaskLoader(tmp_path)
        t = loader.get_task("test_task_alpha")
        assert t["task_id"] == "test_task_alpha"
        assert t["group"] == "test_group"

    def test_list_group(self, tmp_path: Path):
        t1 = _make_task(task_id="a1", group="grp_a")
        t2 = _make_task(task_id="a2", group="grp_a")
        t3 = _make_task(task_id="b1", group="grp_b")
        for t in [t1, t2, t3]:
            _write_task(tmp_path, t)
        loader = TaskLoader(tmp_path)
        assert len(loader.list_group("grp_a")) == 2
        assert len(loader.list_group("grp_b")) == 1
        assert len(loader.list_group("nonexistent")) == 0

    def test_multiple_tasks(self, tmp_path: Path):
        for i in range(5):
            _write_task(tmp_path, _make_task(task_id=f"task_{i}"))
        loader = TaskLoader(tmp_path)
        assert len(loader.list_tasks()) == 5

    def test_optional_defaults_filled(self, tmp_path: Path):
        task = _make_task()
        task.pop("forbidden_signals", None)
        task.pop("routing_expectation", None)
        _write_task(tmp_path, task)
        loader = TaskLoader(tmp_path)
        t = loader.get_task("test_task_alpha")
        assert t["forbidden_signals"] == []
        assert t["routing_expectation"] == {}

    def test_session_setup_defaults_filled(self, tmp_path: Path):
        task = _make_task()
        task["input"]["session_setup"] = {}
        _write_task(tmp_path, task)
        loader = TaskLoader(tmp_path)
        t = loader.get_task("test_task_alpha")
        assert t["input"]["session_setup"]["uploads"] == []
        assert t["input"]["session_setup"]["workspace_files"] == []
        assert t["input"]["session_setup"]["history_seed"] == []

    def test_extra_top_level_fields_allowed(self, tmp_path: Path):
        task = _make_task(notes="这是一个备注", tags=["tag1", "tag2"])
        _write_task(tmp_path, task)
        loader = TaskLoader(tmp_path)
        t = loader.get_task("test_task_alpha")
        assert t["notes"] == "这是一个备注"

    def test_eval_type_routing(self, tmp_path: Path):
        task = _make_task(eval_type="routing")
        _write_task(tmp_path, task)
        loader = TaskLoader(tmp_path)
        assert loader.get_task("test_task_alpha")["eval_type"] == "routing"

    def test_input_patterns_preserved_as_extension(self, tmp_path: Path):
        """input_patterns 作为扩展字段保留，不影响加载"""
        task = _make_task(input_patterns=["分析csv"])
        _write_task(tmp_path, task)
        loader = TaskLoader(tmp_path)
        t = loader.get_task("test_task_alpha")
        assert t["input_patterns"] == ["分析csv"]

    def test_verifier_related_fields_preserved(self, tmp_path: Path):
        task = _make_task(
            output_contract={"format": "json_only"},
            ground_truth={"answer": "ok"},
            verifier={
                "mode": "rubric",
                "target": "final_response_json",
                "checks": [{"id": "answer", "type": "exact_match", "path": "answer"}],
            },
        )
        _write_task(tmp_path, task)
        loader = TaskLoader(tmp_path)
        loaded = loader.get_task("test_task_alpha")
        assert loaded["output_contract"]["format"] == "json_only"
        assert loaded["ground_truth"]["answer"] == "ok"
        assert loaded["verifier"]["target"] == "final_response_json"

    def test_verifier_expected_from_ground_truth_passes_validation(self, tmp_path: Path):
        task = _make_task(
            ground_truth={"nested": {"answer": "ok"}},
            verifier={
                "mode": "rubric",
                "target": "final_response_json",
                "checks": [{
                    "id": "answer",
                    "type": "exact_match",
                    "path": "answer",
                    "expected_from": "nested.answer",
                }],
            },
        )
        _write_task(tmp_path, task)
        loader = TaskLoader(tmp_path)
        loaded = loader.get_task("test_task_alpha")
        assert loaded["verifier"]["checks"][0]["expected_from"] == "nested.answer"

    def test_defaults_not_shared_across_tasks(self, tmp_path: Path):
        """多个 task 的默认值应各自独立，不共享可变对象"""
        t1 = _make_task(task_id="iso_a")
        t1.pop("forbidden_signals", None)
        t1["input"]["session_setup"] = {}
        t2 = _make_task(task_id="iso_b")
        t2.pop("forbidden_signals", None)
        t2["input"]["session_setup"] = {}
        _write_task(tmp_path, t1)
        _write_task(tmp_path, t2)
        loader = TaskLoader(tmp_path)
        a = loader.get_task("iso_a")
        b = loader.get_task("iso_b")
        a["forbidden_signals"].append("mutated")
        assert b["forbidden_signals"] == []
        a["input"]["session_setup"]["uploads"].append("injected.csv")
        assert b["input"]["session_setup"]["uploads"] == []


# ── 必填字段缺失 ──────────────────────────────────────────

class TestMissingRequired:
    """缺少必填字段时应抛错"""

    @pytest.mark.parametrize("field", [
        "task_id", "group", "eval_type", "description", "input",
        "variants", "target_skills", "expected_signals",
        "expected_artifacts", "pass_criteria", "scoring_weights",
    ])
    def test_missing_top_level_field(self, tmp_path: Path, field: str):
        task = _make_task()
        del task[field]
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match=f"缺少必填字段: {field}"):
            TaskLoader(tmp_path)

    def test_missing_user_query(self, tmp_path: Path):
        task = _make_task()
        del task["input"]["user_query"]
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match="input 缺少必填字段: user_query"):
            TaskLoader(tmp_path)

    def test_missing_session_setup(self, tmp_path: Path):
        task = _make_task()
        del task["input"]["session_setup"]
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match="input 缺少必填字段: session_setup"):
            TaskLoader(tmp_path)


# ── 类型错误 ──────────────────────────────────────────────

class TestTypeErrors:
    """字段类型错误时应抛错"""

    def test_task_id_not_string(self, tmp_path: Path):
        task = _make_task(task_id=123)
        _write_task(tmp_path, task, filename="bad.json")
        with pytest.raises(TaskLoadError, match="类型错误"):
            TaskLoader(tmp_path)

    def test_variants_not_list(self, tmp_path: Path):
        task = _make_task(variants="no_skill")
        _write_task(tmp_path, task, filename="bad.json")
        with pytest.raises(TaskLoadError, match="类型错误"):
            TaskLoader(tmp_path)

    def test_scoring_weights_non_numeric(self, tmp_path: Path):
        task = _make_task(scoring_weights={"task_success": "high"})
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match="scoring_weights.*必须是数值"):
            TaskLoader(tmp_path)

    def test_pass_criteria_tool_errors_max_not_int(self, tmp_path: Path):
        task = _make_task()
        task["pass_criteria"]["tool_errors_max"] = 1.5
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match="pass_criteria.tool_errors_max 必须是 int"):
            TaskLoader(tmp_path)

    @pytest.mark.parametrize("field", [
        "variants", "target_skills", "expected_signals", "expected_artifacts",
    ])
    def test_str_list_element_not_string(self, tmp_path: Path, field: str):
        task = _make_task()
        task[field] = ["valid_str", 123]
        _write_task(tmp_path, task, filename="bad.json")
        with pytest.raises(TaskLoadError, match=rf"{field}\[1\] 必须是 str"):
            TaskLoader(tmp_path)

    def test_forbidden_signals_element_not_string(self, tmp_path: Path):
        task = _make_task(forbidden_signals=["ok", 42])
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match=r"forbidden_signals\[1\] 必须是 str"):
            TaskLoader(tmp_path)

    def test_workspace_files_element_not_string(self, tmp_path: Path):
        task = _make_task()
        task["input"]["session_setup"]["workspace_files"] = ["ok.txt", 999]
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match="workspace_files 中包含非字符串元素"):
            TaskLoader(tmp_path)

    def test_verifier_must_be_object(self, tmp_path: Path):
        task = _make_task(verifier=["bad"])
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match="可选字段 'verifier' 类型错误"):
            TaskLoader(tmp_path)

    def test_verifier_expected_from_must_be_string(self, tmp_path: Path):
        task = _make_task(
            ground_truth={"answer": "ok"},
            verifier={
                "mode": "rubric",
                "target": "final_response_json",
                "checks": [{"id": "answer", "type": "exact_match", "path": "answer", "expected_from": 1}],
            },
        )
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match="expected_from 必须是 str"):
            TaskLoader(tmp_path)

    def test_verifier_expected_must_match_ground_truth(self, tmp_path: Path):
        task = _make_task(
            ground_truth={"answer": "ok"},
            verifier={
                "mode": "rubric",
                "target": "final_response_json",
                "checks": [{"id": "answer", "type": "exact_match", "path": "answer", "expected": "bad"}],
            },
        )
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match="expected 与 ground_truth.answer 不一致"):
            TaskLoader(tmp_path)

    def test_verifier_missing_expected_and_ground_truth_path_fails(self, tmp_path: Path):
        task = _make_task(
            ground_truth={"other": "ok"},
            verifier={
                "mode": "rubric",
                "target": "final_response_json",
                "checks": [{"id": "answer", "type": "exact_match", "path": "answer"}],
            },
        )
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match="无法从 ground_truth.answer 解析 expected"):
            TaskLoader(tmp_path)

    def test_uploads_element_not_string(self, tmp_path: Path):
        task = _make_task()
        task["input"]["session_setup"]["uploads"] = [True]
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match="uploads 中包含非字符串元素"):
            TaskLoader(tmp_path)


# ── 语义校验 ─────────────────────────────────────────────

class TestSemanticValidation:
    """语义级校验"""

    def test_invalid_eval_type(self, tmp_path: Path):
        task = _make_task(eval_type="chaos")
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match="eval_type.*不合法"):
            TaskLoader(tmp_path)

    def test_empty_variants(self, tmp_path: Path):
        task = _make_task(variants=[])
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match="variants 不能为空"):
            TaskLoader(tmp_path)

    def test_empty_target_skills(self, tmp_path: Path):
        task = _make_task(target_skills=[])
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match="target_skills 不能为空"):
            TaskLoader(tmp_path)

    def test_absolute_upload_path_unix(self, tmp_path: Path):
        task = _make_task()
        task["input"]["session_setup"]["uploads"] = ["/etc/passwd"]
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match="不能是绝对路径"):
            TaskLoader(tmp_path)

    def test_absolute_upload_path_windows(self, tmp_path: Path):
        task = _make_task()
        task["input"]["session_setup"]["uploads"] = ["C:\\data\\file.csv"]
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match="不能是绝对路径"):
            TaskLoader(tmp_path)

    @pytest.mark.parametrize("bad_path", [
        "../secret.csv",
        "csv/../../etc/passwd",
        "csv/../../../x",
    ])
    def test_upload_path_traversal(self, tmp_path: Path, bad_path: str):
        task = _make_task()
        task["input"]["session_setup"]["uploads"] = [bad_path]
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match="路径包含穿越"):
            TaskLoader(tmp_path)

    @pytest.mark.parametrize("bad_path", [
        "../escape.txt",
        "data/../../out.json",
    ])
    def test_workspace_files_path_traversal(self, tmp_path: Path, bad_path: str):
        task = _make_task()
        task["input"]["session_setup"]["workspace_files"] = [bad_path]
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match="路径包含穿越"):
            TaskLoader(tmp_path)

    def test_upload_nested_relative_ok(self, tmp_path: Path):
        """子目录 + 非穿越相对路径应通过"""
        task = _make_task()
        task["input"]["session_setup"]["uploads"] = ["csv/subdir/file.csv"]
        _write_task(tmp_path, task)
        loader = TaskLoader(tmp_path)
        assert len(loader.list_tasks()) == 1

    def test_duplicate_task_id(self, tmp_path: Path):
        t1 = _make_task(task_id="dup_id")
        t2 = _make_task(task_id="dup_id")
        _write_task(tmp_path, t1, filename="task_a.json")
        _write_task(tmp_path, t2, filename="task_b.json")
        with pytest.raises(TaskLoadError, match="task_id.*dup_id.*重复"):
            TaskLoader(tmp_path)

    def test_get_nonexistent_task(self, tmp_path: Path):
        _write_task(tmp_path, MINIMAL_VALID_TASK)
        loader = TaskLoader(tmp_path)
        with pytest.raises(TaskLoadError, match="不存在"):
            loader.get_task("no_such_task")

    def test_valid_tolerance_mode(self, tmp_path: Path):
        task = _make_task(
            ground_truth={"val": 100},
            verifier={
                "mode": "rubric",
                "target": "final_response_json",
                "checks": [
                    {"id": "v", "type": "numeric_tolerance", "path": "val",
                     "tolerance": 0.001, "tolerance_mode": "relative", "weight": 1.0}
                ],
            },
        )
        _write_task(tmp_path, task)
        loader = TaskLoader(tmp_path)
        assert len(loader.list_tasks()) == 1

    def test_invalid_tolerance_mode_value(self, tmp_path: Path):
        task = _make_task(
            ground_truth={"val": 100},
            verifier={
                "mode": "rubric",
                "target": "final_response_json",
                "checks": [
                    {"id": "v", "type": "numeric_tolerance", "path": "val",
                     "tolerance": 0.001, "tolerance_mode": "percent", "weight": 1.0}
                ],
            },
        )
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match="tolerance_mode"):
            TaskLoader(tmp_path)

    def test_invalid_tolerance_mode_type(self, tmp_path: Path):
        task = _make_task(
            ground_truth={"val": 100},
            verifier={
                "mode": "rubric",
                "target": "final_response_json",
                "checks": [
                    {"id": "v", "type": "numeric_tolerance", "path": "val",
                     "tolerance": 0.001, "tolerance_mode": 123, "weight": 1.0}
                ],
            },
        )
        _write_task(tmp_path, task)
        with pytest.raises(TaskLoadError, match="tolerance_mode"):
            TaskLoader(tmp_path)


# ── 边界与异常 ────────────────────────────────────────────

class TestEdgeCases:
    """目录不存在、空目录、JSON 语法错误"""

    def test_tasks_dir_not_exist(self, tmp_path: Path):
        with pytest.raises(TaskLoadError, match="目录不存在"):
            TaskLoader(tmp_path / "nonexistent")

    def test_tasks_dir_empty(self, tmp_path: Path):
        empty_dir = tmp_path / "empty_tasks"
        empty_dir.mkdir()
        with pytest.raises(TaskLoadError, match="目录为空"):
            TaskLoader(empty_dir)

    def test_invalid_json(self, tmp_path: Path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "bad.json").write_text("{broken", encoding="utf-8")
        with pytest.raises(TaskLoadError, match="JSON 解析失败"):
            TaskLoader(tmp_path)

    def test_json_not_object(self, tmp_path: Path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "arr.json").write_text("[1,2,3]", encoding="utf-8")
        with pytest.raises(TaskLoadError, match="顶层必须是 object"):
            TaskLoader(tmp_path)

    def test_validate_task_standalone(self, tmp_path: Path):
        """validate_task 可以独立使用"""
        _write_task(tmp_path, MINIMAL_VALID_TASK)
        loader = TaskLoader(tmp_path)

        bad = _make_task()
        del bad["group"]
        with pytest.raises(TaskLoadError, match="缺少必填字段: group"):
            loader.validate_task(bad, "inline-test")


# ── 真实仓库 task 集成 ─────────────────────────────────────

class TestRealTasks:
    """加载仓库中的真实 task 文件"""

    REAL_TASKS_DIR = Path(__file__).resolve().parent.parent / "evaluations" / "tasks"

    @pytest.mark.skipif(
        not (Path(__file__).resolve().parent.parent / "evaluations" / "tasks").is_dir(),
        reason="仓库 evaluations/tasks 不存在",
    )
    def test_load_all_real_tasks(self):
        loader = TaskLoader(self.REAL_TASKS_DIR)
        tasks = loader.list_tasks()
        assert len(tasks) >= 8

    @pytest.mark.skipif(
        not (Path(__file__).resolve().parent.parent / "evaluations" / "tasks").is_dir(),
        reason="仓库 evaluations/tasks 不存在",
    )
    def test_real_groups(self):
        loader = TaskLoader(self.REAL_TASKS_DIR)
        csv_tasks = loader.list_group("csv_uplift")
        fin_tasks = loader.list_group("finance_uplift")
        assert len(csv_tasks) >= 4
        assert len(fin_tasks) >= 4
