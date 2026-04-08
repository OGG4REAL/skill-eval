"""BenchmarkStore 单元测试"""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from agent_system.evaluation.benchmark_store import BenchmarkStore


def _make_benchmark(
    benchmark_id: str,
    task_id: str = "task_a",
    variants: list[str] | None = None,
    started_at: str = "2026-04-01T00:00:00+00:00",
    cases: list[dict] | None = None,
    aggregates: list[dict] | None = None,
) -> dict:
    variants = variants or ["no_skill", "with_skill"]
    if cases is None:
        cases = [
            {
                "task_id": task_id,
                "variant_id": "no_skill",
                "trial_index": 1,
                "session_id": "sess-a",
                "run_id": "run_a",
                "status": "passed",
                "score": {"weighted_score": 0.8, "scores": {}, "notes": []},
            },
            {
                "task_id": task_id,
                "variant_id": "with_skill",
                "trial_index": 1,
                "session_id": "sess-b",
                "run_id": "run_b",
                "status": "passed",
                "score": {"weighted_score": 1.0, "scores": {}, "notes": []},
            },
        ]
    if aggregates is None:
        aggregates = [
            {"task_id": task_id, "variant_id": "no_skill", "trials": 1,
             "pass_rate": 1.0, "avg_weighted_score": 0.8},
            {"task_id": task_id, "variant_id": "with_skill", "trials": 1,
             "pass_rate": 1.0, "avg_weighted_score": 1.0},
        ]
    return {
        "benchmark_id": benchmark_id,
        "started_at": started_at,
        "finished_at": "2026-04-01T00:10:00+00:00",
        "scope": {"task_id": task_id, "group": None, "all": False,
                  "variants": variants, "trials": 1},
        "summary": {"cases_total": len(cases), "cases_succeeded": len(cases), "cases_failed": 0},
        "cases": cases,
        "aggregates": {"by_task_variant": aggregates},
    }


def _write_bench(runs_dir: Path, bench: dict) -> Path:
    path = runs_dir / f"{bench['benchmark_id']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bench, f, ensure_ascii=False, indent=2)
    return path


# ── 基本读取 ────────────────────────────────────────────

class TestListBenchmarks:
    def test_empty_dir(self, tmp_path):
        store = BenchmarkStore(tmp_path)
        assert store.list_benchmarks() == []

    def test_nonexistent_dir(self, tmp_path):
        store = BenchmarkStore(tmp_path / "nope")
        assert store.list_benchmarks() == []

    def test_lists_all_benchmarks_sorted_by_time(self, tmp_path):
        b1 = _make_benchmark("bench_001", started_at="2026-04-01T10:00:00+00:00")
        b2 = _make_benchmark("bench_002", started_at="2026-04-02T10:00:00+00:00")
        _write_bench(tmp_path, b1)
        _write_bench(tmp_path, b2)
        store = BenchmarkStore(tmp_path)
        result = store.list_benchmarks()
        assert len(result) == 2
        assert result[0]["benchmark_id"] == "bench_002"
        assert result[1]["benchmark_id"] == "bench_001"

    def test_skips_invalid_json(self, tmp_path):
        _write_bench(tmp_path, _make_benchmark("bench_ok"))
        (tmp_path / "broken.json").write_text("{bad json", encoding="utf-8")
        store = BenchmarkStore(tmp_path)
        assert len(store.list_benchmarks()) == 1

    def test_summary_fields_present(self, tmp_path):
        _write_bench(tmp_path, _make_benchmark("bench_x"))
        store = BenchmarkStore(tmp_path)
        item = store.list_benchmarks()[0]
        assert "benchmark_id" in item
        assert "scope" in item
        assert "summary" in item
        assert "_path" in item


class TestLoadBenchmark:
    def test_load_by_id(self, tmp_path):
        _write_bench(tmp_path, _make_benchmark("bench_abc"))
        store = BenchmarkStore(tmp_path)
        bench = store.load_benchmark("bench_abc")
        assert bench["benchmark_id"] == "bench_abc"
        assert "cases" in bench

    def test_not_found_raises_key_error(self, tmp_path):
        store = BenchmarkStore(tmp_path)
        with pytest.raises(KeyError, match="不存在"):
            store.load_benchmark("no_such_id")


class TestLoadLatest:
    def test_returns_latest(self, tmp_path):
        _write_bench(tmp_path, _make_benchmark("b1", started_at="2026-04-01T00:00:00+00:00"))
        _write_bench(tmp_path, _make_benchmark("b2", started_at="2026-04-02T00:00:00+00:00"))
        store = BenchmarkStore(tmp_path)
        latest = store.load_latest()
        assert latest["benchmark_id"] == "b2"

    def test_filter_by_task_id(self, tmp_path):
        _write_bench(tmp_path, _make_benchmark("b1", task_id="task_a",
                                                started_at="2026-04-02T00:00:00+00:00"))
        _write_bench(tmp_path, _make_benchmark("b2", task_id="task_b",
                                                started_at="2026-04-03T00:00:00+00:00"))
        store = BenchmarkStore(tmp_path)
        result = store.load_latest(task_id="task_a")
        assert result["benchmark_id"] == "b1"

    def test_returns_none_when_no_match(self, tmp_path):
        _write_bench(tmp_path, _make_benchmark("b1", task_id="task_a"))
        store = BenchmarkStore(tmp_path)
        assert store.load_latest(task_id="nonexistent") is None


class TestCollectCases:
    def test_collect_all(self, tmp_path):
        _write_bench(tmp_path, _make_benchmark("b1"))
        _write_bench(tmp_path, _make_benchmark("b2"))
        store = BenchmarkStore(tmp_path)
        cases = store.collect_cases()
        assert len(cases) == 4
        assert all("benchmark_id" in c for c in cases)

    def test_collect_specific_benchmarks(self, tmp_path):
        _write_bench(tmp_path, _make_benchmark("b1"))
        _write_bench(tmp_path, _make_benchmark("b2"))
        store = BenchmarkStore(tmp_path)
        cases = store.collect_cases(benchmark_ids=["b1"])
        assert len(cases) == 2
        assert all(c["benchmark_id"] == "b1" for c in cases)


class TestCollectAggregates:
    def test_collect_all(self, tmp_path):
        _write_bench(tmp_path, _make_benchmark("b1"))
        _write_bench(tmp_path, _make_benchmark("b2"))
        store = BenchmarkStore(tmp_path)
        rows = store.collect_aggregates()
        assert len(rows) == 4
        assert all("benchmark_id" in r for r in rows)

    def test_collect_specific(self, tmp_path):
        _write_bench(tmp_path, _make_benchmark("b1"))
        _write_bench(tmp_path, _make_benchmark("b2"))
        store = BenchmarkStore(tmp_path)
        rows = store.collect_aggregates(benchmark_ids=["b2"])
        assert len(rows) == 2
        assert all(r["benchmark_id"] == "b2" for r in rows)
