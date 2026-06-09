from __future__ import annotations

import json

import pytest

from agent_system.evaluation.benchmark_store import BenchmarkStore
from agent_system.evaluation.skill_comparator import SkillComparator
from agent_system.evaluation.task_loader import TaskLoader
from agent_system.evaluation.variant_manager import VariantManager


BASE_TASK = {
    "task_id": "csv_routing_eval",
    "group": "routing_eval",
    "eval_type": "routing",
    "description": "routing smoke",
    "input": {"user_query": "分析这个 csv", "session_setup": {}},
    "variants": ["no_skill", "with_skill", "skill_v1", "skill_v2", "irrelevant_skill"],
    "target_skills": ["csv-data-summarizer"],
    "irrelevant_skills": ["fin-advisor-math"],
    "skill_versions": {
        "skill_v1": {"csv-data-summarizer": "csv-data-summarizer-v1"},
        "skill_v2": {"csv-data-summarizer": "csv-data-summarizer-v2"},
    },
    "expected_signals": ["skill:csv-data-summarizer"],
    "forbidden_signals": ["skill:fin-advisor-math"],
    "expected_artifacts": [],
    "pass_criteria": {"final_response_non_empty": True},
    "scoring_weights": {"result_score": 0.6, "task_success": 0.2},
    "routing_expectation": {"should_activate": ["csv-data-summarizer"]},
}


def test_routing_variant_exposes_skill_without_preinjecting():
    resolved = VariantManager().resolve_variant(BASE_TASK, "with_skill")

    assert resolved["enabled_skills"] == ["csv-data-summarizer"]
    assert resolved["pre_injected_skills"] == []
    assert resolved["routing_enabled"] is True
    assert resolved["expected_use_mode"] == "routed"


def test_versioned_variants_use_explicit_local_skill_mapping():
    manager = VariantManager()

    v1 = manager.resolve_variant(BASE_TASK, "skill_v1")
    v2 = manager.resolve_variant(BASE_TASK, "skill_v2")

    assert v1["enabled_skills"] == ["csv-data-summarizer-v1"]
    assert v1["skill_version_map"] == {"csv-data-summarizer": "v1"}
    assert v2["enabled_skills"] == ["csv-data-summarizer-v2"]
    assert v2["skill_version_map"] == {"csv-data-summarizer": "v2"}


def test_irrelevant_skill_variant_uses_explicit_interference_skill():
    resolved = VariantManager().resolve_variant(BASE_TASK, "irrelevant_skill")

    assert resolved["enabled_skills"] == ["fin-advisor-math"]
    assert resolved["pre_injected_skills"] == ["fin-advisor-math"]
    assert resolved["expected_use_mode"] == "irrelevant_pre_injected"


def test_task_loader_accepts_later_roadmap_task_fields(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "csv_routing_eval.json").write_text(
        json.dumps(BASE_TASK, ensure_ascii=False),
        encoding="utf-8",
    )

    task = TaskLoader(tasks_dir).get_task("csv_routing_eval")

    assert task["skill_versions"]["skill_v1"]["csv-data-summarizer"] == "csv-data-summarizer-v1"
    assert task["irrelevant_skills"] == ["fin-advisor-math"]


def test_comparator_can_compare_skill_v1_to_skill_v2(tmp_path):
    bench = {
        "benchmark_id": "bench_versions",
        "started_at": "2026-04-02T00:00:00+00:00",
        "finished_at": "2026-04-02T00:10:00+00:00",
        "scope": {
            "task_id": "csv_routing_eval",
            "group": None,
            "all": False,
            "variants": ["skill_v1", "skill_v2"],
            "trials": 1,
        },
        "summary": {"cases_total": 2, "cases_succeeded": 2, "cases_failed": 0},
        "cases": [
            {
                "task_id": "csv_routing_eval",
                "variant_id": "skill_v1",
                "variant": {"enabled_skills": ["csv-data-summarizer-v1"]},
            },
            {
                "task_id": "csv_routing_eval",
                "variant_id": "skill_v2",
                "variant": {"enabled_skills": ["csv-data-summarizer-v2"]},
            },
        ],
        "aggregates": {
            "by_task_variant": [
                {
                    "task_id": "csv_routing_eval",
                    "variant_id": "skill_v1",
                    "trials": 1,
                    "pass_rate": 1.0,
                    "result_pass_rate": 1.0,
                    "avg_result_score": 0.6,
                    "avg_weighted_score": 0.7,
                },
                {
                    "task_id": "csv_routing_eval",
                    "variant_id": "skill_v2",
                    "trials": 1,
                    "pass_rate": 1.0,
                    "result_pass_rate": 1.0,
                    "avg_result_score": 0.9,
                    "avg_weighted_score": 0.9,
                },
            ]
        },
    }
    path = tmp_path / "bench_versions.json"
    path.write_text(json.dumps(bench, ensure_ascii=False), encoding="utf-8")

    result = SkillComparator(store=BenchmarkStore(tmp_path), task_loader=None).compare_benchmark_variants(
        "bench_versions",
        baseline_variant="skill_v1",
        target_variant="skill_v2",
    )

    delta = result["comparisons"]["by_task"][0]
    assert delta["baseline_variant"] == "skill_v1"
    assert delta["target_variant"] == "skill_v2"
    assert delta["result_score_uplift"] == pytest.approx(0.3)
    assert delta["normalized_gain"] == pytest.approx(0.75)
