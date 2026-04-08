"""BenchmarkRunner 单元测试 + 轻量集成测试"""
from __future__ import annotations

import copy
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from agent_system.evaluation.benchmark_runner import (
    BenchmarkRunner,
    _sanitize,
)
from agent_system.evaluation.models import RunRecord


# ── 共享 fixtures ─────────────────────────────────────────

MINIMAL_TASK = {
    "task_id": "test_task_a",
    "group": "test_group",
    "eval_type": "uplift",
    "description": "测试",
    "input": {
        "user_query": "hello",
        "session_setup": {"uploads": [], "workspace_files": [], "history_seed": []},
    },
    "variants": ["no_skill", "with_skill"],
    "target_skills": ["csv-data-summarizer"],
    "expected_signals": ["tool:Bash"],
    "forbidden_signals": [],
    "expected_artifacts": [],
    "pass_criteria": {"final_response_non_empty": True},
    "scoring_weights": {"task_success": 0.5, "signal_match": 0.3, "trajectory_quality": 0.2},
}

VERIFIER_TASK = {
    **MINIMAL_TASK,
    "task_id": "test_task_result_first",
    "expected_signals": [],
    "expected_artifacts": [],
    "pass_criteria": {},
    "verifier": {
        "mode": "rubric",
        "target": "final_response_json",
        "checks": [
            {
                "id": "answer",
                "type": "exact_match",
                "path": "answer",
                "expected": "ok",
                "weight": 1.0,
            }
        ],
    },
}

TASK_WITH_UPLOADS = {
    **MINIMAL_TASK,
    "task_id": "test_task_uploads",
    "input": {
        "user_query": "分析 csv",
        "session_setup": {
            "uploads": ["csv/test.csv"],
            "workspace_files": [],
            "history_seed": [],
        },
    },
}

TASK_WITH_WORKSPACE_FILES = {
    **MINIMAL_TASK,
    "task_id": "test_task_ws",
    "input": {
        "user_query": "test",
        "session_setup": {
            "uploads": [],
            "workspace_files": ["extra/file.txt"],
            "history_seed": [],
        },
    },
}

TASK_WITH_HISTORY_SEED = {
    **MINIMAL_TASK,
    "task_id": "test_task_hs",
    "input": {
        "user_query": "test",
        "session_setup": {
            "uploads": [],
            "workspace_files": [],
            "history_seed": [{"role": "user", "content": "hi"}],
        },
    },
}


def _write_task(tasks_dir: Path, task: dict) -> None:
    fname = f"{task['task_id']}.json"
    (tasks_dir / fname).write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_run_outputs(
    sessions_root: Path, session_id: str, run_id: str,
    status: str = "passed", trajectory: list | None = None,
    artifacts: list | None = None, iterations: int = 3,
    tool_calls: int = 5, tool_errors: int = 0,
) -> None:
    run_dir = sessions_root / session_id / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    run_data = {
        "run_id": run_id,
        "session_id": session_id,
        "task_id": "test_task_a",
        "variant_id": "with_skill",
        "status": status,
        "iterations": iterations,
        "tool_calls": tool_calls,
        "tool_errors": tool_errors,
        "duration_ms": 5000,
        "skills": [],
        "user_input": "hello",
        "enabled_skills": ["csv-data-summarizer"],
        "skill_version_map": {},
        "routing_enabled": True,
    }
    (run_dir / "run.json").write_text(json.dumps(run_data), encoding="utf-8")

    traj = trajectory or [
        {"type": "tool_call_started", "run_id": run_id, "tool_name": "Bash", "arguments": {}},
        {"type": "tool_call_finished", "run_id": run_id, "tool_name": "Bash", "status": "success"},
    ]
    lines = [json.dumps(evt) for evt in traj]
    (run_dir / "trajectory.jsonl").write_text("\n".join(lines), encoding="utf-8")

    art_data = {"run_id": run_id, "files": artifacts or []}
    (run_dir / "artifacts.json").write_text(json.dumps(art_data), encoding="utf-8")


# ── 1. session_id 生成 ───────────────────────────────────

class TestSessionIdGeneration:

    def test_contains_task_variant_trial(self):
        sid = BenchmarkRunner._build_session_id("bench_001", "csv_task", "no_skill", 1)
        assert "csv-task" in sid
        assert "no-skill" in sid
        assert "t1" in sid

    def test_sanitize_special_chars(self):
        assert _sanitize("hello world!") == "hello-world"
        assert _sanitize("a/b\\c") == "a-b-c"

    def test_different_trials_different_ids(self):
        s1 = BenchmarkRunner._build_session_id("b1", "t1", "v1", 1)
        s2 = BenchmarkRunner._build_session_id("b1", "t1", "v1", 2)
        assert s1 != s2

    def test_session_id_matches_derive_session_id(self):
        """_build_session_id 结果经过 derive_session_id 后不变（幂等）"""
        from agent_system.session import derive_session_id
        sid = BenchmarkRunner._build_session_id("bench_20260401_100126_abc", "csv_task", "no_skill", 1)
        derived = derive_session_id("ignored.log", explicit=sid)
        assert sid == derived

    def test_session_id_no_underscores(self):
        """session_id 不应包含下划线（与 session.py 规范一致）"""
        sid = BenchmarkRunner._build_session_id("bench_001", "csv_task", "no_skill", 1)
        assert "_" not in sid

    def test_fixture_dir_matches_agent_dir(self, tmp_path):
        """fixture 复制目录与 derive_session_id 产出的 session 目录一致"""
        from agent_system.session import sanitize_session_id, derive_session_id, ensure_session_dirs

        sid = BenchmarkRunner._build_session_id(
            "bench_20260401_100126_abc", "csv_analysis_clean", "with_skill", 1
        )
        derived = derive_session_id("ignored.log", explicit=sid)
        assert sid == derived

        sessions_root = tmp_path / "sessions"
        sessions_root.mkdir()

        fixture_base, fixture_uploads, _, _ = ensure_session_dirs(sid, sessions_root=sessions_root)
        agent_base, agent_uploads, _, _ = ensure_session_dirs(derived, sessions_root=sessions_root)

        assert fixture_base == agent_base
        assert fixture_uploads == agent_uploads


# ── 2. variant 展开 ──────────────────────────────────────

class TestVariantExpansion:

    def test_default_variants_from_task(self, tmp_path):
        tasks_dir = tmp_path / "evaluations" / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, MINIMAL_TASK)

        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        runner._workspace = tmp_path
        runner._tasks_dir = tasks_dir
        runner._fixtures_dir = tmp_path / "evaluations" / "fixtures"
        runner._fixtures_dir.mkdir(parents=True)
        runner._output_dir = tmp_path / "output"
        runner._output_dir.mkdir()
        runner._sessions_root = tmp_path / "sessions"
        runner._skills_dir = tmp_path / "skills"
        from agent_system.evaluation.task_loader import TaskLoader
        from agent_system.evaluation.variant_manager import VariantManager
        from agent_system.evaluation.scorer import RuleScorer
        runner._task_loader = TaskLoader(tasks_dir)
        runner._variant_manager = VariantManager()
        runner._scorer = RuleScorer()

        task = runner._task_loader.get_task("test_task_a")
        variant_ids = list(task["variants"])
        assert set(variant_ids) == {"no_skill", "with_skill"}

    def test_explicit_variant_overrides(self):
        task = copy.deepcopy(MINIMAL_TASK)
        task["variants"] = ["no_skill", "with_skill", "skill_v1"]
        explicit = ["no_skill"]
        assert explicit == ["no_skill"]

    def test_run_group_per_task_variants(self, tmp_path):
        """run_group 不传 variants 时，每个 task 用自己声明的 variants 展开"""
        tasks_dir = tmp_path / "evaluations" / "tasks"
        tasks_dir.mkdir(parents=True)
        fixtures_dir = tmp_path / "evaluations" / "fixtures"
        fixtures_dir.mkdir(parents=True)
        output_dir = tmp_path / "evaluations" / "benchmarks" / "runs"
        output_dir.mkdir(parents=True)
        sessions_root = tmp_path / "sessions"
        sessions_root.mkdir()

        task_a = {**MINIMAL_TASK, "task_id": "grp_a", "group": "g", "variants": ["no_skill"]}
        task_b = {**MINIMAL_TASK, "task_id": "grp_b", "group": "g", "variants": ["no_skill", "with_skill"]}
        _write_task(tasks_dir, task_a)
        _write_task(tasks_dir, task_b)

        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        runner._workspace = tmp_path
        runner._tasks_dir = tasks_dir
        runner._fixtures_dir = fixtures_dir
        runner._output_dir = output_dir
        runner._sessions_root = sessions_root
        runner._skills_dir = tmp_path / "skills"

        from agent_system.evaluation.task_loader import TaskLoader
        from agent_system.evaluation.variant_manager import VariantManager
        from agent_system.evaluation.scorer import RuleScorer
        runner._task_loader = TaskLoader(tasks_dir)
        runner._variant_manager = VariantManager()
        runner._scorer = RuleScorer()

        run_id = "run_grp_001"
        fake_agent = MagicMock()
        fake_agent.run.return_value = {"response": "OK", "run_id": run_id}
        fake_agent._mcp_client = MagicMock()

        def fake_setup(**kwargs):
            sid = kwargs.get("session_id", "unknown")
            _write_run_outputs(sessions_root, sid, run_id)
            return fake_agent

        with patch("agent_system.main.setup_system", side_effect=fake_setup):
            result = runner.run_group("g", trials=1)

        case_keys = [(c["task_id"], c["variant_id"]) for c in result["cases"]]
        assert ("grp_a", "no_skill") in case_keys
        assert ("grp_b", "no_skill") in case_keys
        assert ("grp_b", "with_skill") in case_keys
        assert ("grp_a", "with_skill") not in case_keys
        assert result["summary"]["cases_total"] == 3


# ── 3. skill_v1/v2 resolve 失败记录 error ────────────────

class TestVariantResolveFail:

    def test_skill_v1_records_error(self, tmp_path):
        tasks_dir = tmp_path / "evaluations" / "tasks"
        tasks_dir.mkdir(parents=True)
        task = {**MINIMAL_TASK, "variants": ["skill_v1"]}
        _write_task(tasks_dir, task)

        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        runner._workspace = tmp_path
        runner._tasks_dir = tasks_dir
        runner._fixtures_dir = tmp_path / "evaluations" / "fixtures"
        runner._fixtures_dir.mkdir(parents=True)
        runner._output_dir = tmp_path / "output"
        runner._output_dir.mkdir()
        runner._sessions_root = tmp_path / "sessions"
        runner._sessions_root.mkdir()
        runner._skills_dir = tmp_path / "skills"
        from agent_system.evaluation.variant_manager import VariantManager
        runner._variant_manager = VariantManager()
        runner._scorer = MagicMock()

        case = runner._run_single_case(task, "skill_v1", 1, "bench_test")
        assert case["status"] == "failed"
        assert "variant resolve 失败" in case["error"]
        assert case["run_id"] is None


# ── 4. aggregation ───────────────────────────────────────

class TestAggregation:

    def test_pass_rate_and_avg_score(self):
        cases = [
            {
                "task_id": "t1", "variant_id": "v1", "status": "passed",
                "duration_ms": 5000, "tool_calls": 8, "tool_errors": 0,
                "score": {
                    "weighted_score": 0.8,
                    "result_score": 1.0,
                    "result_pass": True,
                    "scores": {},
                    "notes": [],
                },
            },
            {
                "task_id": "t1", "variant_id": "v1", "status": "passed",
                "duration_ms": 3000, "tool_calls": 6, "tool_errors": 1,
                "score": {
                    "weighted_score": 0.6,
                    "result_score": 0.5,
                    "result_pass": False,
                    "scores": {},
                    "notes": [],
                },
            },
            {
                "task_id": "t1", "variant_id": "v1", "status": "failed",
                "duration_ms": None, "tool_calls": None, "tool_errors": None,
                "score": None,
            },
        ]
        agg = BenchmarkRunner._aggregate_cases(cases)
        tv = agg["by_task_variant"]
        assert len(tv) == 1
        assert tv[0]["trials"] == 3
        assert tv[0]["pass_rate"] == pytest.approx(2 / 3, abs=0.01)
        assert tv[0]["result_pass_rate"] == pytest.approx(0.5, abs=0.01)
        assert tv[0]["avg_result_score"] == pytest.approx(0.75, abs=0.01)
        assert tv[0]["avg_weighted_score"] == pytest.approx(0.7, abs=0.01)
        assert tv[0]["avg_duration_ms"] == pytest.approx(4000, abs=1)
        assert tv[0]["avg_tool_calls"] == pytest.approx(7, abs=0.1)
        assert tv[0]["avg_tool_errors"] == pytest.approx(0.5, abs=0.1)

    def test_multi_task_variant_groups(self):
        cases = [
            {"task_id": "t1", "variant_id": "v1", "status": "passed",
             "duration_ms": 1000, "tool_calls": 2, "tool_errors": 0,
             "score": {"weighted_score": 1.0, "scores": {}, "notes": []}},
            {"task_id": "t1", "variant_id": "v2", "status": "passed",
             "duration_ms": 2000, "tool_calls": 4, "tool_errors": 1,
             "score": {"weighted_score": 0.5, "scores": {}, "notes": []}},
            {"task_id": "t2", "variant_id": "v1", "status": "failed",
             "duration_ms": None, "tool_calls": None, "tool_errors": None,
             "score": None},
        ]
        agg = BenchmarkRunner._aggregate_cases(cases)
        assert len(agg["by_task_variant"]) == 3

    def test_empty_cases(self):
        agg = BenchmarkRunner._aggregate_cases([])
        assert agg["by_task_variant"] == []

    def test_all_failed_no_metrics(self):
        cases = [
            {"task_id": "t1", "variant_id": "v1", "status": "failed",
             "duration_ms": None, "tool_calls": None, "tool_errors": None,
             "score": None},
        ]
        agg = BenchmarkRunner._aggregate_cases(cases)
        tv = agg["by_task_variant"][0]
        assert tv["avg_weighted_score"] is None
        assert tv["avg_duration_ms"] is None
        assert tv["avg_tool_calls"] is None
        assert tv["avg_tool_errors"] is None


# ── 5. fixture 准备 ──────────────────────────────────────

class TestFixturePreparation:

    def test_upload_copies_to_session(self, tmp_path):
        fixtures_dir = tmp_path / "evaluations" / "fixtures"
        csv_dir = fixtures_dir / "csv"
        csv_dir.mkdir(parents=True)
        (csv_dir / "test.csv").write_text("a,b\n1,2\n", encoding="utf-8")

        sessions_root = tmp_path / "sessions"
        sessions_root.mkdir()

        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        runner._fixtures_dir = fixtures_dir
        runner._sessions_root = sessions_root

        copied = runner._prepare_upload_fixtures(TASK_WITH_UPLOADS, "test-sess")

        assert len(copied) == 1
        assert (sessions_root / "test-sess" / "uploads" / "test.csv").exists()

    def test_missing_fixture_raises(self, tmp_path):
        fixtures_dir = tmp_path / "evaluations" / "fixtures"
        fixtures_dir.mkdir(parents=True)

        sessions_root = tmp_path / "sessions"
        sessions_root.mkdir()

        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        runner._fixtures_dir = fixtures_dir
        runner._sessions_root = sessions_root

        with pytest.raises(FileNotFoundError, match="fixture 不存在"):
            runner._prepare_upload_fixtures(TASK_WITH_UPLOADS, "test-sess2")

    def test_prepare_case_skills_dir_filters_allowed_skills(self, tmp_path):
        skills_dir = tmp_path / "skills"
        (skills_dir / "csv-data-summarizer").mkdir(parents=True)
        (skills_dir / "csv-data-summarizer" / "SKILL.md").write_text("# csv", encoding="utf-8")
        (skills_dir / "fin-advisor-math").mkdir(parents=True)
        (skills_dir / "fin-advisor-math" / "SKILL.md").write_text("# fin", encoding="utf-8")

        sessions_root = tmp_path / "sessions"
        sessions_root.mkdir()

        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        runner._workspace = tmp_path
        runner._skills_dir = skills_dir
        runner._sessions_root = sessions_root

        case_skills_dir = runner._prepare_case_skills_dir(
            "test-sess",
            ["csv-data-summarizer"],
        )

        assert (case_skills_dir / "csv-data-summarizer" / "SKILL.md").exists()
        assert not (case_skills_dir / "fin-advisor-math").exists()

    def test_prepare_case_skills_dir_empty_for_no_skill(self, tmp_path):
        sessions_root = tmp_path / "sessions"
        sessions_root.mkdir()

        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        runner._workspace = tmp_path
        runner._skills_dir = tmp_path / "skills"
        runner._sessions_root = sessions_root

        case_skills_dir = runner._prepare_case_skills_dir("test-sess", [])

        assert case_skills_dir.exists()
        assert list(case_skills_dir.iterdir()) == []


# ── 6. workspace_files / history_seed 未实现 ─────────────

class TestUnsupportedSetup:

    def test_workspace_files_raises(self):
        with pytest.raises(NotImplementedError, match="workspace_files"):
            BenchmarkRunner._check_unsupported_setup(TASK_WITH_WORKSPACE_FILES)

    def test_history_seed_raises(self):
        with pytest.raises(NotImplementedError, match="history_seed"):
            BenchmarkRunner._check_unsupported_setup(TASK_WITH_HISTORY_SEED)

    def test_empty_setup_ok(self):
        BenchmarkRunner._check_unsupported_setup(MINIMAL_TASK)


# ── 7. load_run_outputs ─────────────────────────────────

class TestLoadRunOutputs:

    def test_load_valid_outputs(self, tmp_path):
        sessions_root = tmp_path / "sessions"
        _write_run_outputs(sessions_root, "s1", "r1")

        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        runner._sessions_root = sessions_root
        rr, traj, arts = runner._load_run_outputs("s1", "r1")

        assert isinstance(rr, RunRecord)
        assert rr.run_id == "r1"
        assert rr.status == "passed"
        assert len(traj) == 2
        assert traj[0]["type"] == "tool_call_started"

    def test_missing_run_json_raises(self, tmp_path):
        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        runner._sessions_root = tmp_path / "sessions"
        with pytest.raises(FileNotFoundError, match="run.json"):
            runner._load_run_outputs("nonexist", "r1")

    def test_missing_trajectory_raises(self, tmp_path):
        """trajectory.jsonl 缺失时应报错而非静默返回空"""
        sessions_root = tmp_path / "sessions"
        run_dir = sessions_root / "s1" / "runs" / "r1"
        run_dir.mkdir(parents=True)
        run_json = {"run_id": "r1", "session_id": "s1", "status": "passed",
                     "iterations": 1, "tool_calls": 1, "tool_errors": 0}
        (run_dir / "run.json").write_text(json.dumps(run_json), encoding="utf-8")
        (run_dir / "artifacts.json").write_text('{"files": []}', encoding="utf-8")

        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        runner._sessions_root = sessions_root
        with pytest.raises(FileNotFoundError, match="trajectory.jsonl"):
            runner._load_run_outputs("s1", "r1")

    def test_missing_artifacts_raises(self, tmp_path):
        """artifacts.json 缺失时应报错而非静默返回空"""
        sessions_root = tmp_path / "sessions"
        run_dir = sessions_root / "s1" / "runs" / "r1"
        run_dir.mkdir(parents=True)
        run_json = {"run_id": "r1", "session_id": "s1", "status": "passed",
                     "iterations": 1, "tool_calls": 1, "tool_errors": 0}
        (run_dir / "run.json").write_text(json.dumps(run_json), encoding="utf-8")
        (run_dir / "trajectory.jsonl").write_text('{"type":"test"}\n', encoding="utf-8")

        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        runner._sessions_root = sessions_root
        with pytest.raises(FileNotFoundError, match="artifacts.json"):
            runner._load_run_outputs("s1", "r1")


# ── 8. 轻量集成测试（mock agent） ────────────────────────

class TestIntegrationMocked:

    def _setup_runner(self, tmp_path):
        """构造一个完整的 runner，指向 tmp_path 下的目录"""
        tasks_dir = tmp_path / "evaluations" / "tasks"
        tasks_dir.mkdir(parents=True)
        _write_task(tasks_dir, MINIMAL_TASK)
        _write_task(tasks_dir, VERIFIER_TASK)

        fixtures_dir = tmp_path / "evaluations" / "fixtures"
        fixtures_dir.mkdir(parents=True)

        output_dir = tmp_path / "evaluations" / "benchmarks" / "runs"
        output_dir.mkdir(parents=True)

        sessions_root = tmp_path / "sessions"
        sessions_root.mkdir()

        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        runner._workspace = tmp_path
        runner._tasks_dir = tasks_dir
        runner._fixtures_dir = fixtures_dir
        runner._output_dir = output_dir
        runner._sessions_root = sessions_root
        runner._skills_dir = tmp_path / "skills"

        from agent_system.evaluation.task_loader import TaskLoader
        from agent_system.evaluation.variant_manager import VariantManager
        from agent_system.evaluation.scorer import RuleScorer
        runner._task_loader = TaskLoader(tasks_dir)
        runner._variant_manager = VariantManager()
        runner._scorer = RuleScorer()

        return runner, sessions_root

    def test_run_task_produces_benchmark_json(self, tmp_path):
        runner, sessions_root = self._setup_runner(tmp_path)
        run_id = "run_mock_001"

        fake_agent = MagicMock()
        fake_agent.run.return_value = {
            "response": "分析完成",
            "run_id": run_id,
            "iterations": 3,
            "client_side_tools": [],
        }
        fake_agent._mcp_client = MagicMock()

        def fake_setup(**kwargs):
            sid = kwargs.get("session_id", "unknown")
            _write_run_outputs(sessions_root, sid, run_id)
            return fake_agent

        with patch("agent_system.main.setup_system", side_effect=fake_setup):
            result = runner.run_task(
                "test_task_a",
                variants=["no_skill", "with_skill"],
                trials=1,
            )

        assert result["benchmark_id"].startswith("bench_")
        assert result["summary"]["cases_total"] == 2
        assert len(result["cases"]) == 2
        assert "by_task_variant" in result["aggregates"]

        for case in result["cases"]:
            assert "duration_ms" in case
            assert "tool_calls" in case
            assert "tool_errors" in case
            assert "run_status" in case

        agg = result["aggregates"]["by_task_variant"]
        for entry in agg:
            assert "avg_duration_ms" in entry
            assert "avg_tool_calls" in entry
            assert "avg_tool_errors" in entry

        json_files = list(runner._output_dir.glob("*.json"))
        assert len(json_files) == 1

        written = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert written["benchmark_id"] == result["benchmark_id"]

    def test_single_case_failure_doesnt_crash_batch(self, tmp_path):
        runner, sessions_root = self._setup_runner(tmp_path)

        task = copy.deepcopy(MINIMAL_TASK)
        task["variants"] = ["no_skill", "skill_v1"]
        tasks_dir = tmp_path / "evaluations" / "tasks"
        (tasks_dir / "test_task_a.json").write_text(
            json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        from agent_system.evaluation.task_loader import TaskLoader
        runner._task_loader = TaskLoader(tasks_dir)

        run_id = "run_mock_002"
        fake_agent = MagicMock()
        fake_agent.run.return_value = {
            "response": "OK",
            "run_id": run_id,
            "iterations": 2,
            "client_side_tools": [],
        }
        fake_agent._mcp_client = MagicMock()

        def fake_setup(**kwargs):
            sid = kwargs.get("session_id", "unknown")
            _write_run_outputs(sessions_root, sid, run_id)
            return fake_agent

        with patch("agent_system.main.setup_system", side_effect=fake_setup):
            result = runner.run_task("test_task_a", trials=1)

        assert result["summary"]["cases_total"] == 2
        failed_cases = [c for c in result["cases"] if c["status"] == "failed"]
        passed_cases = [c for c in result["cases"] if c["status"] == "passed"]
        assert len(failed_cases) == 1
        assert "variant resolve 失败" in failed_cases[0]["error"]
        assert len(passed_cases) == 1

    def test_task_aware_status_vs_run_status(self, tmp_path):
        """run.status=passed 但 pass_criteria 未满足时，case status 应为 failed"""
        runner, sessions_root = self._setup_runner(tmp_path)
        run_id = "run_mock_003"

        fake_agent = MagicMock()
        fake_agent.run.return_value = {
            "response": "",
            "run_id": run_id,
        }
        fake_agent._mcp_client = MagicMock()

        def fake_setup(**kwargs):
            sid = kwargs.get("session_id", "unknown")
            _write_run_outputs(sessions_root, sid, run_id)
            return fake_agent

        with patch("agent_system.main.setup_system", side_effect=fake_setup):
            result = runner.run_task("test_task_a", variants=["no_skill"], trials=1)

        case = result["cases"][0]
        assert case["run_status"] == "passed"
        assert case["status"] == "failed"
        assert case["score"]["scores"]["task_success"] == 0.0

    def test_pass_rate_reflects_task_success(self, tmp_path):
        """pass_rate 应基于 task_success 而非 run.status"""
        runner, sessions_root = self._setup_runner(tmp_path)
        run_id = "run_mock_004"

        call_count = [0]
        fake_agent = MagicMock()

        def fake_run(query, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"response": "OK", "run_id": run_id}
            return {"response": "", "run_id": run_id}

        fake_agent.run = fake_run
        fake_agent._mcp_client = MagicMock()

        def fake_setup(**kwargs):
            sid = kwargs.get("session_id", "unknown")
            _write_run_outputs(sessions_root, sid, run_id)
            return fake_agent

        with patch("agent_system.main.setup_system", side_effect=fake_setup):
            result = runner.run_task("test_task_a", variants=["no_skill"], trials=2)

        passed = [c for c in result["cases"] if c["status"] == "passed"]
        failed = [c for c in result["cases"] if c["status"] == "failed"]
        assert len(passed) == 1
        assert len(failed) == 1
        assert all(c["run_status"] == "passed" for c in result["cases"])

        agg_entry = result["aggregates"]["by_task_variant"][0]
        assert agg_entry["pass_rate"] == pytest.approx(0.5, abs=0.01)

    def test_runner_passes_final_response_text_into_verifier(self, tmp_path):
        runner, sessions_root = self._setup_runner(tmp_path)
        run_id = "run_mock_result_001"

        fake_agent = MagicMock()
        fake_agent.run.return_value = {
            "response": '{"answer":"ok"}',
            "run_id": run_id,
        }
        fake_agent._mcp_client = MagicMock()

        def fake_setup(**kwargs):
            sid = kwargs.get("session_id", "unknown")
            _write_run_outputs(sessions_root, sid, run_id)
            return fake_agent

        with patch("agent_system.main.setup_system", side_effect=fake_setup):
            result = runner.run_task("test_task_result_first", variants=["no_skill"], trials=1)

        case = result["cases"][0]
        assert case["status"] == "passed"
        assert case["final_response_present"] is True
        assert case["score"]["result_score"] == 1.0
        assert case["score"]["result_pass"] is True
        assert case["score"]["result_detail"]["summary"]["passed_checks"] == 1

        agg_entry = result["aggregates"]["by_task_variant"][0]
        assert agg_entry["avg_result_score"] == pytest.approx(1.0, abs=0.01)
        assert agg_entry["result_pass_rate"] == pytest.approx(1.0, abs=0.01)


# ── 9. sessions_root 透传 ────────────────────────────────

class TestSessionsRootPassthrough:
    """验证 sessions_root 从 runner 一路到 Agent/RunRecorder 的透传"""

    def test_agent_recorder_writes_to_custom_sessions_root(self, tmp_path):
        """Agent 传入自定义 sessions_root 后，run.json 落在该目录下"""
        from agent_system.agent.core import Agent
        from agent_system.tools.base import ToolRegistry
        from agent_system.skills.manager import SkillManager

        custom_root = tmp_path / "custom_sessions"
        custom_root.mkdir()
        session_id = "bench-test-sess"
        session_dir = custom_root / session_id
        session_dir.mkdir()
        log_file = session_dir / "chat_history.log"
        log_file.touch()

        sm = MagicMock(spec=SkillManager)
        sm.list_skills.return_value = []
        sm.get_skills_for_tool_description.return_value = ""
        tr = ToolRegistry()

        with patch("agent_system.agent.core.Config") as mock_cfg:
            mock_cfg.SESSIONS_ROOT = tmp_path / "default_sessions"
            mock_cfg.WORKSPACE_ROOT = tmp_path
            mock_cfg.PERSISTED_OUTPUT_THRESHOLD = 8192
            mock_cfg.PERSISTED_OUTPUT_PREVIEW_SIZE = 2048
            mock_cfg.TOOL_RESULTS_DIR_NAME = ".tool-results"
            mock_cfg.CONTEXT_TOKEN_BUDGET = 100000

            agent = Agent(
                skill_manager=sm,
                tool_registry=tr,
                log_file=str(log_file),
                sessions_root=custom_root,
            )
            assert agent.sessions_root == custom_root

            recorder = agent._init_recorder("test query")
            recorder.finalize(status="passed", iterations=1)

        run_json = custom_root / session_id / "runs" / recorder.run_id / "run.json"
        assert run_json.exists(), f"run.json 应该在自定义 sessions_root 下: {run_json}"

        default_run = tmp_path / "default_sessions" / session_id / "runs" / recorder.run_id / "run.json"
        assert not default_run.exists(), "run.json 不应该落在默认 Config.SESSIONS_ROOT 下"

    def test_agent_default_sessions_root_when_none(self, tmp_path):
        """不传 sessions_root 时应回退到 Config.SESSIONS_ROOT"""
        from agent_system.agent.core import Agent
        from agent_system.tools.base import ToolRegistry
        from agent_system.skills.manager import SkillManager

        default_root = tmp_path / "default_sessions"
        default_root.mkdir()
        session_id = "normal-sess"
        session_dir = default_root / session_id
        session_dir.mkdir()
        log_file = session_dir / "chat_history.log"
        log_file.touch()

        sm = MagicMock(spec=SkillManager)
        sm.list_skills.return_value = []
        sm.get_skills_for_tool_description.return_value = ""
        tr = ToolRegistry()

        with patch("agent_system.agent.core.Config") as mock_cfg:
            mock_cfg.SESSIONS_ROOT = default_root
            mock_cfg.WORKSPACE_ROOT = tmp_path
            mock_cfg.PERSISTED_OUTPUT_THRESHOLD = 8192
            mock_cfg.PERSISTED_OUTPUT_PREVIEW_SIZE = 2048
            mock_cfg.TOOL_RESULTS_DIR_NAME = ".tool-results"
            mock_cfg.CONTEXT_TOKEN_BUDGET = 100000

            agent = Agent(
                skill_manager=sm,
                tool_registry=tr,
                log_file=str(log_file),
            )
            assert agent.sessions_root == default_root

            recorder = agent._init_recorder("test query")
            recorder.finalize(status="passed", iterations=1)

        run_json = default_root / session_id / "runs" / recorder.run_id / "run.json"
        assert run_json.exists()

    def test_benchmark_runner_e2e_unified_paths(self, tmp_path):
        """benchmark runner 端到端：fixture 和 run 产出在同一个 sessions_root"""
        from agent_system.evaluation.task_loader import TaskLoader
        from agent_system.evaluation.variant_manager import VariantManager
        from agent_system.evaluation.scorer import RuleScorer
        from agent_system.agent.core import Agent
        from agent_system.tools.base import ToolRegistry
        from agent_system.skills.manager import SkillManager

        tasks_dir = tmp_path / "evaluations" / "tasks"
        tasks_dir.mkdir(parents=True)
        fixtures_dir = tmp_path / "evaluations" / "fixtures"
        csv_dir = fixtures_dir / "csv"
        csv_dir.mkdir(parents=True)
        (csv_dir / "test.csv").write_text("a,b\n1,2\n", encoding="utf-8")

        output_dir = tmp_path / "evaluations" / "benchmarks" / "runs"
        output_dir.mkdir(parents=True)
        sessions_root = tmp_path / "sessions"
        sessions_root.mkdir()

        task = {
            **MINIMAL_TASK,
            "task_id": "e2e_path_test",
            "input": {
                "user_query": "分析 csv",
                "session_setup": {
                    "uploads": ["csv/test.csv"],
                    "workspace_files": [],
                    "history_seed": [],
                },
            },
        }
        _write_task(tasks_dir, task)

        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        runner._workspace = tmp_path
        runner._tasks_dir = tasks_dir
        runner._fixtures_dir = fixtures_dir
        runner._output_dir = output_dir
        runner._sessions_root = sessions_root
        runner._skills_dir = tmp_path / "skills"
        runner._task_loader = TaskLoader(tasks_dir)
        runner._variant_manager = VariantManager()
        runner._scorer = RuleScorer()

        run_id = "run_e2e_001"

        def fake_setup(**kwargs):
            sid = kwargs.get("session_id", "unknown")
            sr = kwargs.get("sessions_root")

            assert sr == sessions_root, (
                f"setup_system 应该收到 runner 的 sessions_root={sessions_root}，"
                f"实际收到: {sr}"
            )

            session_dir = sr / sid
            session_dir.mkdir(parents=True, exist_ok=True)
            log_file = session_dir / "chat_history.log"
            log_file.touch()

            sm = MagicMock(spec=SkillManager)
            sm.list_skills.return_value = []
            sm.get_skills_for_tool_description.return_value = ""
            tr = ToolRegistry()

            agent = Agent(
                skill_manager=sm,
                tool_registry=tr,
                log_file=str(log_file),
                sessions_root=sr,
                variant_context=kwargs.get("variant_context"),
            )

            recorder = agent._init_recorder("分析 csv")
            actual_run_id = recorder.run_id
            recorder.finalize(status="passed", iterations=2)

            agent.run = MagicMock(return_value={
                "response": "分析完成",
                "run_id": actual_run_id,
            })
            agent._mcp_client = MagicMock()
            return agent

        with patch("agent_system.main.setup_system", side_effect=fake_setup):
            result = runner.run_task("e2e_path_test", variants=["no_skill"], trials=1)

        case = result["cases"][0]
        assert case["error"] is None, f"case 不应有错误: {case['error']}"
        assert case["run_id"] is not None

        sid = case["session_id"]
        assert (sessions_root / sid / "uploads" / "test.csv").exists(), \
            "fixture 应在 runner 的 sessions_root 下"
        assert (sessions_root / sid / "runs" / case["run_id"] / "run.json").exists(), \
            "run.json 应在 runner 的 sessions_root 下"
        assert (sessions_root / sid / "runs" / case["run_id"] / "trajectory.jsonl").exists(), \
            "trajectory.jsonl 应在 runner 的 sessions_root 下"
        assert (sessions_root / sid / "runs" / case["run_id"] / "artifacts.json").exists(), \
            "artifacts.json 应在 runner 的 sessions_root 下"
