from __future__ import annotations

import json

import pytest

from agent_system.evaluation.benchmark_store import BenchmarkStore
from agent_system.evaluation.models import RunRecord
from agent_system.evaluation.scorer import RuleScorer
from agent_system.evaluation.skill_comparator import SkillComparator


def test_verifier_failure_is_repeatable_task_failure():
    task = {
        "task_id": "regression_bad_result",
        "pass_criteria": {},
        "expected_signals": [],
        "expected_artifacts": [],
        "scoring_weights": {"result_score": 0.8, "task_success": 0.2},
        "verifier": {
            "mode": "rubric",
            "target": "final_response_json",
            "checks": [
                {
                    "id": "answer",
                    "type": "exact_match",
                    "path": "answer",
                    "expected": "expected",
                }
            ],
        },
    }
    run = RunRecord(
        run_id="run_bad",
        session_id="sess_bad",
        task_id="regression_bad_result",
        variant_id="with_skill",
        status="passed",
    )

    record = RuleScorer().score_task_run(
        task=task,
        run=run,
        trajectory=[],
        artifacts=[],
        final_response_present=True,
        final_response_text='{"answer":"actual"}',
    )

    assert record.scores["result_score"] == 0.0
    assert record.metrics["result_pass"] is False
    assert record.scores["task_success"] == 0.0


def test_failed_case_contract_keeps_debug_lab_run_ref(tmp_path):
    bench = {
        "benchmark_id": "bench_failed_case",
        "started_at": "2026-04-02T00:00:00+00:00",
        "finished_at": "2026-04-02T00:10:00+00:00",
        "scope": {
            "task_id": "regression_bad_result",
            "group": None,
            "all": False,
            "variants": ["with_skill"],
            "trials": 1,
        },
        "summary": {"cases_total": 1, "cases_succeeded": 0, "cases_failed": 1},
        "cases": [
            {
                "task_id": "regression_bad_result",
                "variant_id": "with_skill",
                "trial_index": 1,
                "session_id": "sess_bad",
                "run_id": "run_bad",
                "status": "failed",
                "run_status": "passed",
                "score": {
                    "result_score": 0.0,
                    "result_pass": False,
                    "result_detail": {"failure_reason": "exact mismatch"},
                    "notes": ["result verifier failed"],
                },
            }
        ],
        "aggregates": {
            "by_task_variant": [
                {
                    "task_id": "regression_bad_result",
                    "variant_id": "with_skill",
                    "trials": 1,
                    "pass_rate": 0.0,
                    "result_pass_rate": 0.0,
                    "avg_result_score": 0.0,
                    "avg_weighted_score": 0.0,
                }
            ]
        },
    }
    (tmp_path / "bench_failed_case.json").write_text(
        json.dumps(bench, ensure_ascii=False),
        encoding="utf-8",
    )

    detail = BenchmarkStore(tmp_path).load_benchmark_contract("bench_failed_case")

    assert "cases" not in detail
    assert detail["failed_cases"][0]["session_id"] == "sess_bad"
    assert detail["failed_cases"][0]["run_id"] == "run_bad"
    assert detail["failed_cases"][0]["failure_reason"] == "exact mismatch"


def test_negative_gain_task_is_marked_and_visible_to_comparator(tmp_path):
    bench = {
        "benchmark_id": "bench_negative_gain",
        "started_at": "2026-04-02T00:00:00+00:00",
        "finished_at": "2026-04-02T00:10:00+00:00",
        "scope": {
            "task_id": "regression_negative_gain",
            "group": None,
            "all": False,
            "variants": ["no_skill", "with_skill"],
            "trials": 1,
        },
        "summary": {"cases_total": 2, "cases_succeeded": 1, "cases_failed": 1},
        "cases": [
            {"task_id": "regression_negative_gain", "variant_id": "no_skill", "variant": {"enabled_skills": []}},
            {
                "task_id": "regression_negative_gain",
                "variant_id": "with_skill",
                "variant": {"enabled_skills": ["csv-data-summarizer"]},
            },
        ],
        "aggregates": {
            "by_task_variant": [
                {
                    "task_id": "regression_negative_gain",
                    "variant_id": "no_skill",
                    "trials": 1,
                    "pass_rate": 1.0,
                    "result_pass_rate": 1.0,
                    "avg_result_score": 0.9,
                    "avg_weighted_score": 0.9,
                },
                {
                    "task_id": "regression_negative_gain",
                    "variant_id": "with_skill",
                    "trials": 1,
                    "pass_rate": 0.0,
                    "result_pass_rate": 0.0,
                    "avg_result_score": 0.4,
                    "avg_weighted_score": 0.5,
                },
            ]
        },
    }
    (tmp_path / "bench_negative_gain.json").write_text(
        json.dumps(bench, ensure_ascii=False),
        encoding="utf-8",
    )

    result = SkillComparator(store=BenchmarkStore(tmp_path), task_loader=None).compare_benchmark(
        "bench_negative_gain"
    )

    delta = result["comparisons"]["by_task"][0]
    assert delta["result_score_uplift"] == pytest.approx(-0.5)
    assert delta["verdict"] == "negative"
    assert result["comparisons"]["by_skill"][0]["negative_tasks"] == ["regression_negative_gain"]
