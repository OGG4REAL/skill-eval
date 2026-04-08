"""SkillComparator 单元测试"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_system.evaluation.benchmark_store import BenchmarkStore
from agent_system.evaluation.skill_comparator import (
    SkillComparator,
    _safe_diff,
    _verdict,
    _extract_skill_map_from_cases,
    _write_comparison_json,
)


def _make_bench(
    benchmark_id: str = "bench_001",
    task_id: str = "csv_analysis_clean_general",
    no_skill_result_score: float | None = None,
    with_skill_result_score: float | None = None,
    no_skill_score: float = 0.8,
    with_skill_score: float = 1.0,
    no_skill_result_pass_rate: float | None = None,
    with_skill_result_pass_rate: float | None = None,
    no_skill_pass_rate: float = 1.0,
    with_skill_pass_rate: float = 1.0,
    no_skill_duration: float = 20000,
    with_skill_duration: float = 50000,
    extra_agg: list[dict] | None = None,
) -> dict:
    agg = [
        {"task_id": task_id, "variant_id": "no_skill", "trials": 1,
         "pass_rate": no_skill_pass_rate, "result_pass_rate": no_skill_result_pass_rate,
         "avg_result_score": no_skill_result_score, "avg_weighted_score": no_skill_score,
         "avg_duration_ms": no_skill_duration, "avg_tool_calls": 3, "avg_tool_errors": 0},
        {"task_id": task_id, "variant_id": "with_skill", "trials": 1,
         "pass_rate": with_skill_pass_rate, "result_pass_rate": with_skill_result_pass_rate,
         "avg_result_score": with_skill_result_score, "avg_weighted_score": with_skill_score,
         "avg_duration_ms": with_skill_duration, "avg_tool_calls": 4, "avg_tool_errors": 0},
    ]
    if extra_agg:
        agg.extend(extra_agg)
    return {
        "benchmark_id": benchmark_id,
        "started_at": "2026-04-02T00:00:00+00:00",
        "finished_at": "2026-04-02T00:10:00+00:00",
        "scope": {"task_id": task_id, "group": None, "all": False,
                  "variants": ["no_skill", "with_skill"], "trials": 1},
        "summary": {"cases_total": 2, "cases_succeeded": 2, "cases_failed": 0},
        "cases": [],
        "aggregates": {"by_task_variant": agg},
    }


def _write_bench(runs_dir: Path, bench: dict) -> Path:
    path = runs_dir / f"{bench['benchmark_id']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bench, f, ensure_ascii=False, indent=2)
    return path


# ── 工具函数 ────────────────────────────────────────────

class TestHelpers:
    def test_safe_diff(self):
        assert _safe_diff(1.0, 0.8) == pytest.approx(0.2)
        assert _safe_diff(None, 0.8) is None
        assert _safe_diff(1.0, None) is None

    def test_verdict(self):
        assert _verdict(0.05) == "positive"
        assert _verdict(-0.05) == "negative"
        assert _verdict(0.005) == "neutral"
        assert _verdict(0.0) == "neutral"
        assert _verdict(None) == "N/A"


# ── 单 benchmark 比较 ──────────────────────────────────

class TestCompareBenchmark:
    def test_basic_uplift(self, tmp_path):
        bench = _make_bench(
            no_skill_result_score=0.7,
            with_skill_result_score=1.0,
            no_skill_result_pass_rate=0.5,
            with_skill_result_pass_rate=1.0,
            no_skill_score=0.8,
            with_skill_score=1.0,
        )
        _write_bench(tmp_path, bench)
        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=None)
        result = comp.compare_benchmark("bench_001")

        assert result["source"] == "bench_001"
        assert result["baseline_variant"] == "no_skill"
        assert result["target_variant"] == "with_skill"

        by_task = result["comparisons"]["by_task"]
        assert len(by_task) == 1
        delta = by_task[0]
        assert delta["task_id"] == "csv_analysis_clean_general"
        assert delta["baseline_result_score"] == pytest.approx(0.7)
        assert delta["target_result_score"] == pytest.approx(1.0)
        assert delta["result_score_uplift"] == pytest.approx(0.3)
        assert delta["baseline_result_pass_rate"] == pytest.approx(0.5)
        assert delta["target_result_pass_rate"] == pytest.approx(1.0)
        assert delta["baseline_score"] == pytest.approx(0.8)
        assert delta["target_score"] == pytest.approx(1.0)
        assert delta["score_uplift"] == pytest.approx(0.2)
        assert delta["verdict"] == "positive"

    def test_negative_uplift(self, tmp_path):
        bench = _make_bench(
            no_skill_result_score=1.0,
            with_skill_result_score=0.6,
            no_skill_score=1.0,
            with_skill_score=0.7,
        )
        _write_bench(tmp_path, bench)
        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=None)
        result = comp.compare_benchmark("bench_001")

        delta = result["comparisons"]["by_task"][0]
        assert delta["result_score_uplift"] == pytest.approx(-0.4)
        assert delta["score_uplift"] == pytest.approx(-0.3)
        assert delta["verdict"] == "negative"

    def test_neutral_uplift(self, tmp_path):
        bench = _make_bench(no_skill_score=0.9, with_skill_score=0.9)
        _write_bench(tmp_path, bench)
        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=None)
        result = comp.compare_benchmark("bench_001")

        delta = result["comparisons"]["by_task"][0]
        assert delta["score_uplift"] == pytest.approx(0.0)
        assert delta["verdict"] == "neutral"

    def test_missing_baseline_skips_task(self, tmp_path):
        """只有 with_skill 没有 no_skill 时跳过该 task"""
        bench = _make_bench()
        bench["aggregates"]["by_task_variant"] = [
            {"task_id": "t1", "variant_id": "with_skill", "trials": 1,
             "pass_rate": 1.0, "avg_weighted_score": 0.9},
        ]
        _write_bench(tmp_path, bench)
        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=None)
        result = comp.compare_benchmark("bench_001")
        assert result["comparisons"]["by_task"] == []

    def test_duration_diff(self, tmp_path):
        bench = _make_bench(no_skill_duration=20000, with_skill_duration=60000)
        _write_bench(tmp_path, bench)
        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=None)
        result = comp.compare_benchmark("bench_001")
        delta = result["comparisons"]["by_task"][0]
        assert delta["duration_diff_ms"] == pytest.approx(40000)


# ── Skill-level 汇总 ──────────────────────────────────

class TestSkillSummary:
    def test_single_skill_summary(self, tmp_path):
        bench = _make_bench(
            no_skill_result_score=0.7,
            with_skill_result_score=1.0,
            no_skill_score=0.8,
            with_skill_score=1.0,
        )
        _write_bench(tmp_path, bench)

        mock_loader = MagicMock()
        mock_loader.get_task.return_value = {"target_skills": ["csv-data-summarizer"]}

        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=mock_loader)
        result = comp.compare_benchmark("bench_001")

        by_skill = result["comparisons"]["by_skill"]
        assert len(by_skill) == 1
        assert by_skill[0]["skill"] == "csv-data-summarizer"
        assert by_skill[0]["tasks"] == 1
        assert by_skill[0]["baseline_result_avg"] == pytest.approx(0.7)
        assert by_skill[0]["target_result_avg"] == pytest.approx(1.0)
        assert by_skill[0]["avg_result_score_uplift"] == pytest.approx(0.3)
        assert by_skill[0]["baseline_avg"] == pytest.approx(0.8)
        assert by_skill[0]["skill_avg"] == pytest.approx(1.0)
        assert by_skill[0]["avg_uplift"] == pytest.approx(0.2)
        assert by_skill[0]["positive_tasks"] == ["csv_analysis_clean_general"]
        assert by_skill[0]["negative_tasks"] == []

    def test_multi_task_multi_skill(self, tmp_path):
        bench = _make_bench(
            no_skill_score=0.8, with_skill_score=0.95,
            extra_agg=[
                {"task_id": "finance_aip", "variant_id": "no_skill", "trials": 1,
                 "pass_rate": 0.5, "avg_weighted_score": 0.6},
                {"task_id": "finance_aip", "variant_id": "with_skill", "trials": 1,
                 "pass_rate": 1.0, "avg_weighted_score": 0.9},
            ],
        )
        _write_bench(tmp_path, bench)

        def fake_get_task(task_id):
            mapping = {
                "csv_analysis_clean_general": {"target_skills": ["csv-data-summarizer"]},
                "finance_aip": {"target_skills": ["fin-advisor-math"]},
            }
            return mapping[task_id]

        mock_loader = MagicMock()
        mock_loader.get_task.side_effect = fake_get_task

        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=mock_loader)
        result = comp.compare_benchmark("bench_001")

        by_skill = result["comparisons"]["by_skill"]
        assert len(by_skill) == 2
        skills = {s["skill"] for s in by_skill}
        assert skills == {"csv-data-summarizer", "fin-advisor-math"}

    def test_negative_delta_tasks(self, tmp_path):
        bench = _make_bench(no_skill_score=1.0, with_skill_score=0.5)
        _write_bench(tmp_path, bench)

        mock_loader = MagicMock()
        mock_loader.get_task.return_value = {"target_skills": ["csv-data-summarizer"]}

        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=mock_loader)
        result = comp.compare_benchmark("bench_001")

        by_skill = result["comparisons"]["by_skill"]
        assert by_skill[0]["negative_tasks"] == ["csv_analysis_clean_general"]
        assert by_skill[0]["positive_tasks"] == []

    def test_verdict_threshold_consistency(self, tmp_path):
        """skill summary 的 positive/negative/neutral 必须与 task-level verdict 一致"""
        bench = _make_bench(no_skill_score=0.95, with_skill_score=0.955)
        _write_bench(tmp_path, bench)

        mock_loader = MagicMock()
        mock_loader.get_task.return_value = {"target_skills": ["csv-data-summarizer"]}

        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=mock_loader)
        result = comp.compare_benchmark("bench_001")

        delta = result["comparisons"]["by_task"][0]
        assert delta["verdict"] == "neutral", "uplift=0.005 应该是 neutral（阈值 0.01）"

        by_skill = result["comparisons"]["by_skill"][0]
        assert by_skill["neutral_tasks"] == ["csv_analysis_clean_general"]
        assert by_skill["positive_tasks"] == []
        assert by_skill["negative_tasks"] == []


# ── skill 映射来源 ──────────────────────────────────────

class TestSkillMapFromCases:
    def test_extract_from_cases(self):
        cases = [
            {"task_id": "t1", "variant_id": "no_skill", "variant": {"enabled_skills": []}},
            {"task_id": "t1", "variant_id": "with_skill",
             "variant": {"enabled_skills": ["csv-data-summarizer"]}},
            {"task_id": "t2", "variant_id": "with_skill",
             "variant": {"enabled_skills": ["fin-advisor-math"]}},
        ]
        m = _extract_skill_map_from_cases(cases)
        assert m == {"t1": "csv-data-summarizer", "t2": "fin-advisor-math"}

    def test_empty_cases(self):
        assert _extract_skill_map_from_cases([]) == {}

    def test_no_enabled_skills_skips(self):
        cases = [
            {"task_id": "t1", "variant_id": "no_skill", "variant": {"enabled_skills": []}},
        ]
        assert _extract_skill_map_from_cases(cases) == {}

    def test_benchmark_snapshot_over_task_loader(self, tmp_path):
        """skill 归属应优先取 benchmark 快照，不读当前 task 定义"""
        bench = _make_bench(no_skill_score=0.8, with_skill_score=1.0)
        bench["cases"] = [
            {"task_id": "csv_analysis_clean_general", "variant_id": "no_skill",
             "variant": {"enabled_skills": []}},
            {"task_id": "csv_analysis_clean_general", "variant_id": "with_skill",
             "variant": {"enabled_skills": ["csv-data-summarizer"]}},
        ]
        _write_bench(tmp_path, bench)

        mock_loader = MagicMock()
        mock_loader.get_task.return_value = {"target_skills": ["CHANGED-skill-name"]}

        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=mock_loader)
        result = comp.compare_benchmark("bench_001")

        delta = result["comparisons"]["by_task"][0]
        assert delta["skill"] == "csv-data-summarizer", \
            "应从 benchmark cases 快照取 skill，而非当前 TaskLoader"

        mock_loader.get_task.assert_not_called()

    def test_compare_all_uses_winning_benchmark_skill(self, tmp_path):
        """compare_all 的 skill 映射必须来自 winning benchmark，不被旧 benchmark 污染"""
        b_old = _make_bench("b_old", task_id="t1",
                            no_skill_score=0.5, with_skill_score=0.6)
        b_old["started_at"] = "2026-04-01T00:00:00+00:00"
        b_old["cases"] = [
            {"task_id": "t1", "variant_id": "with_skill",
             "variant": {"enabled_skills": ["OLD-skill-name"]}},
            {"task_id": "t1", "variant_id": "no_skill",
             "variant": {"enabled_skills": []}},
        ]
        _write_bench(tmp_path, b_old)

        b_new = _make_bench("b_new", task_id="t1",
                            no_skill_score=0.9, with_skill_score=1.0)
        b_new["started_at"] = "2026-04-02T00:00:00+00:00"
        b_new["cases"] = [
            {"task_id": "t1", "variant_id": "with_skill",
             "variant": {"enabled_skills": ["NEW-skill-name"]}},
            {"task_id": "t1", "variant_id": "no_skill",
             "variant": {"enabled_skills": []}},
        ]
        _write_bench(tmp_path, b_new)

        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=None)
        result = comp.compare_all()

        delta = result["comparisons"]["by_task"][0]
        assert delta["skill"] == "NEW-skill-name", \
            "应取 winning benchmark (b_new) 的 skill，不是 b_old 的"
        assert delta["baseline_score"] == pytest.approx(0.9)

    def test_compare_all_prefers_with_skill_benchmark_for_skill_mapping(self, tmp_path):
        """当 no_skill / with_skill 来自不同 benchmark 时，skill 归属应跟随 with_skill 的 winning row。"""
        b_old = _make_bench("b_old", task_id="t1",
                            no_skill_score=0.5, with_skill_score=0.8)
        b_old["started_at"] = "2026-04-01T00:00:00+00:00"
        b_old["aggregates"]["by_task_variant"] = [
            {"task_id": "t1", "variant_id": "with_skill", "trials": 1,
             "pass_rate": 1.0, "avg_weighted_score": 0.8,
             "avg_duration_ms": 50000, "avg_tool_calls": 4, "avg_tool_errors": 0},
        ]
        b_old["cases"] = [
            {"task_id": "t1", "variant_id": "with_skill",
             "variant": {"enabled_skills": ["OLD-with-skill"]}},
        ]
        _write_bench(tmp_path, b_old)

        b_new = _make_bench("b_new", task_id="t1",
                            no_skill_score=0.9, with_skill_score=1.0)
        b_new["started_at"] = "2026-04-02T00:00:00+00:00"
        b_new["aggregates"]["by_task_variant"] = [
            {"task_id": "t1", "variant_id": "no_skill", "trials": 1,
             "pass_rate": 1.0, "avg_weighted_score": 0.9,
             "avg_duration_ms": 20000, "avg_tool_calls": 3, "avg_tool_errors": 0},
        ]
        b_new["cases"] = [
            {"task_id": "t1", "variant_id": "no_skill",
             "variant": {"enabled_skills": []}},
        ]
        _write_bench(tmp_path, b_new)

        mock_loader = MagicMock()
        mock_loader.get_task.return_value = {"target_skills": ["TASKLOADER-skill"]}

        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=mock_loader)
        result = comp.compare_all()

        delta = result["comparisons"]["by_task"][0]
        assert delta["baseline_score"] == pytest.approx(0.9)
        assert delta["target_score"] == pytest.approx(0.8)
        assert delta["skill"] == "OLD-with-skill"
        mock_loader.get_task.assert_not_called()

    def test_multi_skill_warning(self, tmp_path):
        """task 关联多个 skill 时必须产出显式警告，不静默折叠"""
        bench = _make_bench(no_skill_score=0.8, with_skill_score=1.0)
        bench["cases"] = [
            {"task_id": "csv_analysis_clean_general", "variant_id": "no_skill",
             "variant": {"enabled_skills": []}},
            {"task_id": "csv_analysis_clean_general", "variant_id": "with_skill",
             "variant": {"enabled_skills": ["skill-a", "skill-b"]}},
        ]
        _write_bench(tmp_path, bench)

        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=None)
        result = comp.compare_benchmark("bench_001")

        assert "warnings" in result
        assert any("多个 skill" in w for w in result["warnings"])
        delta = result["comparisons"]["by_task"][0]
        assert delta["skill"] in ("skill-a", "skill-b")

    def test_multi_skill_warning_from_task_loader(self, tmp_path):
        """TaskLoader 兜底时多 skill 也必须警告"""
        bench = _make_bench(no_skill_score=0.8, with_skill_score=1.0)
        bench["cases"] = []
        _write_bench(tmp_path, bench)

        mock_loader = MagicMock()
        mock_loader.get_task.return_value = {
            "target_skills": ["skill-x", "skill-y", "skill-z"]
        }

        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=mock_loader)
        result = comp.compare_benchmark("bench_001")

        assert "warnings" in result
        assert any("多个 target_skills" in w for w in result["warnings"])

    def test_no_warning_for_single_skill(self, tmp_path):
        """单 skill task 不应产出警告"""
        bench = _make_bench(no_skill_score=0.8, with_skill_score=1.0)
        bench["cases"] = [
            {"task_id": "csv_analysis_clean_general", "variant_id": "with_skill",
             "variant": {"enabled_skills": ["csv-data-summarizer"]}},
        ]
        _write_bench(tmp_path, bench)

        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=None)
        result = comp.compare_benchmark("bench_001")

        assert "warnings" not in result


# ── compare_latest / compare_all ────────────────────────

class TestCompareLatestAndAll:
    def test_compare_latest(self, tmp_path):
        _write_bench(tmp_path, _make_bench("b1", no_skill_score=0.7, with_skill_score=0.9))
        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=None)
        result = comp.compare_latest()
        assert result["source"] == "b1"
        assert len(result["comparisons"]["by_task"]) == 1

    def test_compare_latest_no_match(self, tmp_path):
        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=None)
        with pytest.raises(ValueError, match="没有找到"):
            comp.compare_latest()

    def test_compare_all(self, tmp_path):
        _write_bench(tmp_path, _make_bench("b1", task_id="t1",
                                            no_skill_score=0.7, with_skill_score=0.9))
        _write_bench(tmp_path, _make_bench("b2", task_id="t2",
                                            no_skill_score=0.5, with_skill_score=0.8))
        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=None)
        result = comp.compare_all()
        assert result["source"] == "all_benchmarks"
        assert len(result["comparisons"]["by_task"]) == 2

    def test_compare_all_keeps_newest(self, tmp_path):
        """跨 benchmark 同 (task, variant) 取最新一条，不被旧数据覆盖"""
        _write_bench(tmp_path, _make_bench(
            "b_old", task_id="t1",
            no_skill_score=0.5, with_skill_score=0.6,
        ))
        old = json.loads((tmp_path / "b_old.json").read_text(encoding="utf-8"))
        old["started_at"] = "2026-04-01T00:00:00+00:00"
        with open(tmp_path / "b_old.json", "w", encoding="utf-8") as f:
            json.dump(old, f)

        _write_bench(tmp_path, _make_bench(
            "b_new", task_id="t1",
            no_skill_score=0.9, with_skill_score=1.0,
        ))
        new = json.loads((tmp_path / "b_new.json").read_text(encoding="utf-8"))
        new["started_at"] = "2026-04-02T00:00:00+00:00"
        with open(tmp_path / "b_new.json", "w", encoding="utf-8") as f:
            json.dump(new, f)

        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=None)
        result = comp.compare_all()
        delta = result["comparisons"]["by_task"][0]
        assert delta["baseline_score"] == pytest.approx(0.9)
        assert delta["target_score"] == pytest.approx(1.0)

    def test_compare_all_empty(self, tmp_path):
        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=None)
        with pytest.raises(ValueError, match="没有找到"):
            comp.compare_all()


# ── 报告输出 ────────────────────────────────────────────

class TestFormatReport:
    def test_report_contains_key_info(self, tmp_path):
        bench = _make_bench(no_skill_score=0.8, with_skill_score=1.0)
        _write_bench(tmp_path, bench)
        store = BenchmarkStore(tmp_path)
        comp = SkillComparator(store=store, task_loader=None)
        result = comp.compare_benchmark("bench_001")

        report = SkillComparator.format_report(result)
        assert "Skill Uplift Report" in report
        assert "csv_analysis_clean_general" in report
        assert "positive" in report

    def test_report_empty_deltas(self):
        result = {
            "source": "test",
            "baseline_variant": "no_skill",
            "target_variant": "with_skill",
            "comparisons": {"by_task": [], "by_skill": []},
        }
        report = SkillComparator.format_report(result)
        assert "Skill Uplift Report" in report

    def test_report_includes_warnings(self):
        result = {
            "source": "test",
            "baseline_variant": "no_skill",
            "target_variant": "with_skill",
            "warnings": ["task 't1' 关联多个 skill (a, b)，当前仅取首个用于归因"],
            "comparisons": {"by_task": [], "by_skill": []},
        }
        report = SkillComparator.format_report(result)
        assert "Warnings" in report
        assert "多个 skill" in report


# ── JSON 输出 ────────────────────────────────────────────

class TestWriteComparisonJson:
    def test_writes_file(self, tmp_path):
        result = {
            "source": "bench_001",
            "comparisons": {"by_task": [], "by_skill": []},
        }
        path = _write_comparison_json(result, tmp_path)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["source"] == "bench_001"

    def test_creates_output_dir(self, tmp_path):
        output_dir = tmp_path / "sub" / "dir"
        result = {"source": "test", "comparisons": {}}
        path = _write_comparison_json(result, output_dir)
        assert path.exists()


# ── 与真实 TaskLoader 集成 ──────────────────────────────

class TestTaskLoaderIntegration:
    def test_resolve_skill_from_task_loader(self, tmp_path):
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        task = {
            "task_id": "csv_analysis_clean_general",
            "group": "csv_uplift",
            "eval_type": "uplift",
            "description": "测试",
            "input": {"user_query": "分析 csv", "session_setup": {}},
            "variants": ["no_skill", "with_skill"],
            "target_skills": ["csv-data-summarizer"],
            "expected_signals": [],
            "expected_artifacts": [],
            "pass_criteria": {},
            "scoring_weights": {"task_success": 0.5, "signal_match": 0.5},
        }
        with open(tasks_dir / "csv_analysis_clean_general.json", "w", encoding="utf-8") as f:
            json.dump(task, f, ensure_ascii=False)

        bench = _make_bench(no_skill_score=0.8, with_skill_score=1.0)
        _write_bench(runs_dir, bench)

        from agent_system.evaluation.task_loader import TaskLoader
        store = BenchmarkStore(runs_dir)
        loader = TaskLoader(tasks_dir)
        comp = SkillComparator(store=store, task_loader=loader)
        result = comp.compare_benchmark("bench_001")

        by_task = result["comparisons"]["by_task"]
        assert by_task[0]["skill"] == "csv-data-summarizer"

        by_skill = result["comparisons"]["by_skill"]
        assert by_skill[0]["skill"] == "csv-data-summarizer"
