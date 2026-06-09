"""Evaluation API contract smoke tests"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _make_benchmark(
    benchmark_id: str = "bench_api",
    task_id: str = "csv_analysis_clean_general",
) -> dict:
    return {
        "benchmark_id": benchmark_id,
        "started_at": "2026-04-02T00:00:00+00:00",
        "finished_at": "2026-04-02T00:10:00+00:00",
        "scope": {
            "task_id": task_id,
            "group": None,
            "all": False,
            "variants": ["no_skill", "with_skill"],
            "trials": 1,
        },
        "summary": {
            "cases_total": 2,
            "cases_succeeded": 2,
            "cases_failed": 0,
        },
        "cases": [
            {
                "task_id": task_id,
                "variant_id": "no_skill",
                "trial_index": 1,
                "session_id": "sess-a",
                "run_id": "run_a",
                "status": "passed",
                "run_status": "passed",
                "variant": {"enabled_skills": []},
                "score": {
                    "weighted_score": 0.8,
                    "result_score": 0.7,
                    "result_pass": True,
                    "scores": {},
                    "notes": [],
                },
            },
            {
                "task_id": task_id,
                "variant_id": "with_skill",
                "trial_index": 1,
                "session_id": "sess-b",
                "run_id": "run_b",
                "status": "passed",
                "run_status": "passed",
                "variant": {"enabled_skills": ["csv-data-summarizer"]},
                "score": {
                    "weighted_score": 1.0,
                    "result_score": 1.0,
                    "result_pass": True,
                    "scores": {},
                    "notes": [],
                },
            },
        ],
        "aggregates": {
            "by_task_variant": [
                {
                    "task_id": task_id,
                    "variant_id": "no_skill",
                    "trials": 1,
                    "pass_rate": 1.0,
                    "result_pass_rate": 1.0,
                    "avg_result_score": 0.7,
                    "avg_weighted_score": 0.8,
                    "avg_duration_ms": 1000,
                    "avg_tool_calls": 2,
                    "avg_tool_errors": 0,
                },
                {
                    "task_id": task_id,
                    "variant_id": "with_skill",
                    "trials": 1,
                    "pass_rate": 1.0,
                    "result_pass_rate": 1.0,
                    "avg_result_score": 1.0,
                    "avg_weighted_score": 1.0,
                    "avg_duration_ms": 1200,
                    "avg_tool_calls": 3,
                    "avg_tool_errors": 0,
                },
            ]
        },
    }


def _write_benchmark(root: Path, bench: dict) -> None:
    runs_dir = root / "evaluations" / "benchmarks" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / f"{bench['benchmark_id']}.json").write_text(
        json.dumps(bench, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _make_task(task_id: str = "task_api_import", description: str = "imported task") -> dict:
    return {
        "task_id": task_id,
        "group": "api",
        "eval_type": "uplift",
        "description": description,
        "input": {
            "user_query": "Summarize the CSV",
            "session_setup": {
                "uploads": [],
                "workspace_files": [],
                "history_seed": [],
            },
        },
        "variants": ["no_skill", "with_skill"],
        "target_skills": ["csv-data-summarizer"],
        "expected_signals": [],
        "expected_artifacts": [],
        "pass_criteria": {"final_response_non_empty": True},
        "scoring_weights": {"result": 1.0},
        "ground_truth": {"summary": "ok"},
        "verifier": {
            "kind": "result",
            "checks": [
                {"path": "summary", "expected_from": "summary"},
            ],
        },
    }


@pytest.fixture
def api_context(monkeypatch, tmp_path):
    import server.app as app_module

    monkeypatch.setattr(app_module.Config, "WORKSPACE_ROOT", tmp_path)
    return TestClient(app_module.app), tmp_path, app_module


def test_overview_empty_returns_200_empty_state(api_context):
    client, _, _ = api_context

    res = client.get("/evaluation/overview")

    assert res.status_code == 200
    data = res.json()
    assert data["summary"]["benchmark_count"] == 0
    assert data["summary"]["cases_total"] == 0
    assert data["latest_benchmarks"] == []


def test_benchmark_detail_contract_and_404(api_context):
    client, root, _ = api_context
    _write_benchmark(root, _make_benchmark())

    ok = client.get("/evaluation/benchmarks/bench_api")
    missing = client.get("/evaluation/benchmarks/no_such_benchmark")

    assert ok.status_code == 200
    detail = ok.json()
    assert "cases" not in detail
    assert detail["summary"]["pass_rate"] == 1.0
    assert len(detail["matrix"]) == 2
    assert len(detail["run_refs"]) == 2
    assert detail["comparison"]["summary"]["tasks_compared"] == 1
    assert missing.status_code == 404


def test_skill_summary_unknown_skill_returns_empty_200(api_context):
    client, root, _ = api_context
    _write_benchmark(root, _make_benchmark())

    res = client.get("/evaluation/skills/unknown-skill/summary")

    assert res.status_code == 200
    data = res.json()
    assert data["summary"]["skill"] == "unknown-skill"
    assert data["summary"]["tasks_compared"] == 0
    assert data["tasks"] == []


def test_comparisons_default_all_and_benchmark_filter(api_context):
    client, root, _ = api_context
    _write_benchmark(root, _make_benchmark())

    all_res = client.get("/evaluation/comparisons")
    one_res = client.get("/evaluation/comparisons?benchmark_id=bench_api")

    assert all_res.status_code == 200
    assert all_res.json()["summary"]["source"] == "all_benchmarks"
    assert one_res.status_code == 200
    assert one_res.json()["summary"]["source"] == "bench_api"


def test_comparisons_accepts_versioned_variant_pair(api_context):
    client, root, _ = api_context
    bench = _make_benchmark()
    bench["scope"]["variants"] = ["skill_v1", "skill_v2"]
    bench["cases"] = [
        {
            "task_id": "csv_analysis_clean_general",
            "variant_id": "skill_v1",
            "session_id": "sess-v1",
            "run_id": "run_v1",
            "status": "passed",
            "variant": {"enabled_skills": ["csv-data-summarizer-v1"]},
        },
        {
            "task_id": "csv_analysis_clean_general",
            "variant_id": "skill_v2",
            "session_id": "sess-v2",
            "run_id": "run_v2",
            "status": "passed",
            "variant": {"enabled_skills": ["csv-data-summarizer-v2"]},
        },
    ]
    bench["aggregates"]["by_task_variant"] = [
        {
            "task_id": "csv_analysis_clean_general",
            "variant_id": "skill_v1",
            "trials": 1,
            "pass_rate": 1.0,
            "result_pass_rate": 1.0,
            "avg_result_score": 0.6,
            "avg_weighted_score": 0.7,
        },
        {
            "task_id": "csv_analysis_clean_general",
            "variant_id": "skill_v2",
            "trials": 1,
            "pass_rate": 1.0,
            "result_pass_rate": 1.0,
            "avg_result_score": 0.9,
            "avg_weighted_score": 0.9,
        },
    ]
    _write_benchmark(root, bench)

    res = client.get(
        "/evaluation/comparisons"
        "?benchmark_id=bench_api&baseline_variant=skill_v1&target_variant=skill_v2"
    )

    assert res.status_code == 200
    data = res.json()
    assert data["summary"]["baseline_variant"] == "skill_v1"
    assert data["summary"]["target_variant"] == "skill_v2"
    assert data["by_task"][0]["result_score_uplift"] == pytest.approx(0.3)


def test_run_benchmark_request_validation(api_context):
    client, _, _ = api_context

    res = client.post(
        "/evaluation/benchmarks/run",
        json={"task_id": "task_a", "group": "csv"},
    )

    assert res.status_code == 400


def test_import_task_success_and_no_path_leak(api_context):
    client, root, _ = api_context
    from agent_system.evaluation.task_loader import TaskLoader

    task = _make_task()

    res = client.post("/evaluation/tasks/import", json={"task": task})

    assert res.status_code == 200
    data = res.json()
    assert data == {
        "task_id": "task_api_import",
        "group": "api",
        "eval_type": "uplift",
        "target_skills": ["csv-data-summarizer"],
        "variants": ["no_skill", "with_skill"],
        "verifier_configured": True,
    }
    assert "path" not in data
    task_path = root / "evaluations" / "tasks" / "task_api_import.json"
    assert task_path.exists()
    assert json.loads(task_path.read_text(encoding="utf-8"))["task_id"] == "task_api_import"
    assert TaskLoader(root / "evaluations" / "tasks").get_task("task_api_import")["task_id"] == "task_api_import"


def test_import_task_conflict_and_overwrite(api_context):
    client, root, _ = api_context
    tasks_dir = root / "evaluations" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    task_path = tasks_dir / "task_api_import.json"
    task_path.write_text(json.dumps(_make_task(description="old")), encoding="utf-8")

    conflict = client.post("/evaluation/tasks/import", json={"task": _make_task(description="new")})
    overwrite = client.post(
        "/evaluation/tasks/import",
        json={"task": _make_task(description="new"), "overwrite": True},
    )

    assert conflict.status_code == 409
    assert overwrite.status_code == 200
    assert json.loads(task_path.read_text(encoding="utf-8"))["description"] == "new"


def test_import_task_invalid_schema_returns_400(api_context):
    client, root, _ = api_context

    res = client.post("/evaluation/tasks/import", json={"task": {"task_id": "bad_task"}})

    assert res.status_code == 400
    assert str(root) not in res.json()["detail"]


def test_run_benchmark_uses_sync_runner_contract(api_context, monkeypatch):
    client, _, app_module = api_context

    class FakeRunner:
        def __init__(self, workspace_root=None):
            self.workspace_root = workspace_root

        def run_task(self, task_id, variants=None, trials=1):
            assert task_id == "task_api"
            assert variants == ["no_skill"]
            assert trials == 1
            return _make_benchmark("bench_new", task_id=task_id)

    monkeypatch.setattr(app_module, "BenchmarkRunner", FakeRunner)

    res = client.post(
        "/evaluation/benchmarks/run",
        json={
            "task_id": "task_api",
            "variants": ["no_skill"],
            "trials": 1,
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["benchmark_id"] == "bench_new"
    assert data["summary"]["cases_total"] == 2
    assert data["benchmark"]["benchmark_id"] == "bench_new"
