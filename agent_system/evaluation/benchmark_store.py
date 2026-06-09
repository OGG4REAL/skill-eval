"""
Benchmark Store — benchmark 结果的统一读取入口

职责：
- 扫描并加载 evaluations/benchmarks/runs/*.json
- 提供按 benchmark_id / scope 的查询能力
- 把多份 benchmark 的 cases 拉平供 comparator 消费
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import Config


class BenchmarkStore:
    """只读 benchmark 结果仓库，基于文件系统"""

    def __init__(self, runs_dir: Path | None = None):
        self._runs_dir = (
            runs_dir
            or Config.WORKSPACE_ROOT / "evaluations" / "benchmarks" / "runs"
        )

    # ── 公开接口 ─────────────────────────────────────────────

    def list_benchmarks(self) -> list[dict[str, Any]]:
        """列出所有 benchmark 摘要（不含 cases 明细），按时间倒序"""
        results: list[dict[str, Any]] = []
        for path in self._iter_json_files():
            try:
                data = self._read_json(path)
                results.append({
                    "benchmark_id": data["benchmark_id"],
                    "started_at": data.get("started_at"),
                    "finished_at": data.get("finished_at"),
                    "scope": data.get("scope", {}),
                    "summary": data.get("summary", {}),
                    "_path": str(path),
                })
            except Exception:
                continue
        results.sort(key=lambda r: r.get("started_at") or "", reverse=True)
        return results

    def list_benchmark_contracts(self) -> list[dict[str, Any]]:
        """列出 API contract 用 benchmark 摘要，不暴露本地文件路径"""
        results: list[dict[str, Any]] = []
        for item in self.list_benchmarks():
            try:
                data = self.load_benchmark(item["benchmark_id"])
                results.append(self.build_benchmark_list_item(data))
            except Exception:
                continue
        return results

    def load_benchmark(self, benchmark_id: str) -> dict[str, Any]:
        """按 benchmark_id 加载完整 JSON，找不到时抛 KeyError"""
        for path in self._iter_json_files():
            try:
                data = self._read_json(path)
                if data.get("benchmark_id") == benchmark_id:
                    return data
            except Exception:
                continue
        raise KeyError(f"benchmark '{benchmark_id}' 不存在")

    def load_benchmark_contract(
        self,
        benchmark_id: str,
        comparison: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """加载 benchmark detail contract，不透传完整 raw cases"""
        return self.build_benchmark_detail(
            self.load_benchmark(benchmark_id),
            comparison=comparison,
        )

    def load_latest(
        self,
        task_id: str | None = None,
        group: str | None = None,
    ) -> dict[str, Any] | None:
        """加载最新一次 benchmark，可按 scope 中的 task_id / group 过滤"""
        for item in self.list_benchmarks():
            scope = item.get("scope", {})
            if task_id and scope.get("task_id") != task_id:
                continue
            if group and scope.get("group") != group:
                continue
            return self.load_benchmark(item["benchmark_id"])
        return None

    def collect_cases(
        self,
        benchmark_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """跨 benchmark 收集所有 cases 扁平列表，每条附加 benchmark_id 追溯字段"""
        cases: list[dict[str, Any]] = []
        if benchmark_ids is not None:
            sources = [self.load_benchmark(bid) for bid in benchmark_ids]
        else:
            sources = [
                self.load_benchmark(item["benchmark_id"])
                for item in self.list_benchmarks()
            ]
        for bench in sources:
            bid = bench["benchmark_id"]
            for case in bench.get("cases", []):
                cases.append({**case, "benchmark_id": bid})
        return cases

    def collect_aggregates(
        self,
        benchmark_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """跨 benchmark 收集所有 by_task_variant 聚合行，每条附加 benchmark_id"""
        rows: list[dict[str, Any]] = []
        if benchmark_ids is not None:
            sources = [self.load_benchmark(bid) for bid in benchmark_ids]
        else:
            sources = [
                self.load_benchmark(item["benchmark_id"])
                for item in self.list_benchmarks()
            ]
        for bench in sources:
            bid = bench["benchmark_id"]
            agg = bench.get("aggregates", {})
            for row in agg.get("by_task_variant", []):
                rows.append({**row, "benchmark_id": bid})
        return rows

    def build_overview(
        self,
        comparison_summary: dict[str, Any] | None = None,
        latest_limit: int = 5,
    ) -> dict[str, Any]:
        """构建 Overview API contract"""
        benchmarks = self.list_benchmark_contracts()
        task_ids: set[str] = set()
        skill_names: set[str] = set()
        cases_total = 0
        cases_failed = 0

        for item in benchmarks:
            summary = item.get("summary", {})
            cases_total += int(summary.get("cases_total") or 0)
            cases_failed += int(summary.get("cases_failed") or 0)

        for data in self._iter_benchmark_data():
            task_ids.update(self._collect_task_ids(data))
            skill_names.update(self._collect_skill_names(data))

        comparison_summary = comparison_summary or self.empty_comparison_summary()
        skill_count = comparison_summary.get("skills_compared") or len(skill_names)
        latest = benchmarks[0] if benchmarks else None

        warnings: list[str] = []
        if not benchmarks:
            warnings.append("暂无 benchmark 数据")

        return {
            "summary": {
                "benchmark_count": len(benchmarks),
                "task_count": len(task_ids),
                "skill_count": skill_count,
                "latest_benchmark_id": latest["benchmark_id"] if latest else None,
                "latest_started_at": latest["started_at"] if latest else None,
                "cases_total": cases_total,
                "cases_failed": cases_failed,
                "positive_comparisons": comparison_summary.get("positive_tasks", 0),
                "negative_comparisons": comparison_summary.get("negative_tasks", 0),
            },
            "latest_benchmarks": benchmarks[:latest_limit],
            "comparison_summary": comparison_summary,
            "warnings": warnings,
        }

    def list_recent_benchmarks_for_skill(
        self,
        skill: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """列出包含指定 skill 的最近 benchmark 摘要"""
        results: list[dict[str, Any]] = []
        for item in self.list_benchmarks():
            try:
                data = self.load_benchmark(item["benchmark_id"])
            except Exception:
                continue
            if skill in self._collect_skill_names(data):
                results.append(self.build_benchmark_list_item(data))
            if len(results) >= limit:
                break
        return results

    @classmethod
    def build_benchmark_list_item(cls, data: dict[str, Any]) -> dict[str, Any]:
        """把 benchmark raw JSON 转成列表 contract"""
        return {
            "benchmark_id": data.get("benchmark_id"),
            "started_at": data.get("started_at"),
            "finished_at": data.get("finished_at"),
            "scope": cls._normalize_scope(data.get("scope", {})),
            "summary": cls.build_benchmark_summary(data),
        }

    @classmethod
    def build_benchmark_detail(
        cls,
        data: dict[str, Any],
        comparison: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """把 benchmark raw JSON 转成 detail contract"""
        detail = cls.build_benchmark_list_item(data)
        detail.update({
            "matrix": cls._build_matrix(data),
            "failed_cases": cls._build_failed_cases(data),
            "run_refs": cls._build_run_refs(data),
            "comparison": comparison,
        })
        return detail

    @classmethod
    def build_benchmark_summary(cls, data: dict[str, Any]) -> dict[str, Any]:
        raw_summary = data.get("summary", {}) or {}
        cases_total = int(raw_summary.get("cases_total") or 0)
        cases_succeeded = int(raw_summary.get("cases_succeeded") or 0)
        cases_failed = int(raw_summary.get("cases_failed") or 0)
        return {
            "cases_total": cases_total,
            "cases_succeeded": cases_succeeded,
            "cases_failed": cases_failed,
            "pass_rate": round(cases_succeeded / cases_total, 4)
            if cases_total else None,
            "task_count": len(cls._collect_task_ids(data)),
            "variant_count": len(cls._collect_variant_ids(data)),
        }

    @staticmethod
    def empty_comparison_summary(source: str = "all_benchmarks") -> dict[str, Any]:
        return {
            "source": source,
            "generated_at": None,
            "baseline_variant": "no_skill",
            "target_variant": "with_skill",
            "tasks_compared": 0,
            "skills_compared": 0,
            "positive_tasks": 0,
            "negative_tasks": 0,
            "neutral_tasks": 0,
            "avg_result_score_uplift": None,
            "avg_normalized_gain": None,
        }

    # ── 内部方法 ──────────────────────────────────────────────

    def _iter_json_files(self):
        if not self._runs_dir.is_dir():
            return
        yield from sorted(self._runs_dir.glob("*.json"), reverse=True)

    def _iter_benchmark_data(self):
        for path in self._iter_json_files():
            try:
                yield self._read_json(path)
            except Exception:
                continue

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _normalize_scope(scope: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": scope.get("task_id"),
            "group": scope.get("group"),
            "all": bool(scope.get("all", False)),
            "variants": list(scope.get("variants") or []),
            "trials": int(scope.get("trials") or 0),
        }

    @staticmethod
    def _aggregate_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
        return list((data.get("aggregates", {}) or {}).get("by_task_variant", []) or [])

    @classmethod
    def _collect_task_ids(cls, data: dict[str, Any]) -> set[str]:
        task_ids = {
            row.get("task_id")
            for row in cls._aggregate_rows(data)
            if row.get("task_id")
        }
        for case in data.get("cases", []) or []:
            if case.get("task_id"):
                task_ids.add(case["task_id"])
        scope_task = (data.get("scope", {}) or {}).get("task_id")
        if scope_task:
            task_ids.add(scope_task)
        return task_ids

    @classmethod
    def _collect_variant_ids(cls, data: dict[str, Any]) -> set[str]:
        variant_ids = {
            row.get("variant_id")
            for row in cls._aggregate_rows(data)
            if row.get("variant_id")
        }
        for case in data.get("cases", []) or []:
            if case.get("variant_id"):
                variant_ids.add(case["variant_id"])
        for variant_id in (data.get("scope", {}) or {}).get("variants", []) or []:
            if variant_id:
                variant_ids.add(variant_id)
        return variant_ids

    @staticmethod
    def _collect_skill_names(data: dict[str, Any]) -> set[str]:
        skill_names: set[str] = set()
        for case in data.get("cases", []) or []:
            variant = case.get("variant", {}) or {}
            for field in ("enabled_skills", "pre_injected_skills"):
                for skill in variant.get(field, []) or []:
                    if skill:
                        skill_names.add(skill)
        return skill_names

    @classmethod
    def _build_matrix(cls, data: dict[str, Any]) -> list[dict[str, Any]]:
        fields = [
            "task_id",
            "variant_id",
            "trials",
            "pass_rate",
            "result_pass_rate",
            "avg_result_score",
            "avg_weighted_score",
            "avg_duration_ms",
            "avg_tool_calls",
            "avg_tool_errors",
        ]
        return [
            {field: row.get(field) for field in fields}
            for row in cls._aggregate_rows(data)
        ]

    @classmethod
    def _build_failed_cases(cls, data: dict[str, Any]) -> list[dict[str, Any]]:
        failed_cases: list[dict[str, Any]] = []
        for case in data.get("cases", []) or []:
            if cls._case_passed(case):
                continue
            score = case.get("score", {}) or {}
            result_detail = score.get("result_detail", {}) or {}
            failed_cases.append({
                **cls._case_run_ref(case),
                "error": case.get("error"),
                "failure_reason": result_detail.get("failure_reason"),
                "notes": list(score.get("notes") or [])[:5],
            })
        return failed_cases

    @classmethod
    def _build_run_refs(cls, data: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            cls._case_run_ref(case)
            for case in data.get("cases", []) or []
        ]

    @staticmethod
    def _case_passed(case: dict[str, Any]) -> bool:
        score = case.get("score", {}) or {}
        result_pass = score.get("result_pass")
        if result_pass is False:
            return False
        return (
            case.get("status") == "passed"
            and case.get("run_status", "passed") == "passed"
            and not case.get("error")
        )

    @staticmethod
    def _case_run_ref(case: dict[str, Any]) -> dict[str, Any]:
        score = case.get("score", {}) or {}
        return {
            "task_id": case.get("task_id"),
            "variant_id": case.get("variant_id"),
            "trial_index": case.get("trial_index"),
            "session_id": case.get("session_id"),
            "run_id": case.get("run_id"),
            "status": case.get("status"),
            "run_status": case.get("run_status"),
            "result_pass": score.get("result_pass"),
            "result_score": score.get("result_score"),
        }
