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

    # ── 内部方法 ──────────────────────────────────────────────

    def _iter_json_files(self):
        if not self._runs_dir.is_dir():
            return
        yield from sorted(self._runs_dir.glob("*.json"), reverse=True)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
