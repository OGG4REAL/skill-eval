"""
Skill Comparator — 生成 with_skill vs no_skill 的 uplift 分析

职责：
- 基于单次或多次 benchmark 结果，计算 task-level delta
- 汇总 skill-level uplift
- 提供 CLI 入口 + 可读文本输出
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .benchmark_store import BenchmarkStore
from .task_loader import TaskLoader
from ..config import Config


BASELINE_VARIANT = "no_skill"
TARGET_VARIANT = "with_skill"


class SkillComparator:
    """计算 with_skill vs no_skill 的 task-level delta 和 skill-level uplift"""

    def __init__(
        self,
        store: BenchmarkStore | None = None,
        task_loader: TaskLoader | None = None,
        workspace_root: Path | None = None,
    ):
        ws = (workspace_root or Config.WORKSPACE_ROOT).resolve()
        self._store = store or BenchmarkStore(
            ws / "evaluations" / "benchmarks" / "runs"
        )
        try:
            self._task_loader = task_loader or TaskLoader(ws / "evaluations" / "tasks")
        except Exception:
            self._task_loader = None

    # ── 公开接口 ─────────────────────────────────────────────

    def compare_benchmark(self, benchmark_id: str) -> dict[str, Any]:
        """对单次 benchmark 做 with_skill vs no_skill 比较"""
        bench = self._store.load_benchmark(benchmark_id)
        return self._compare_from_benchmark(bench)

    def compare_benchmark_variants(
        self,
        benchmark_id: str,
        baseline_variant: str,
        target_variant: str,
    ) -> dict[str, Any]:
        bench = self._store.load_benchmark(benchmark_id)
        return self._compare_from_benchmark(
            bench,
            baseline_variant=baseline_variant,
            target_variant=target_variant,
        )

    def compare_latest(
        self,
        task_id: str | None = None,
        group: str | None = None,
    ) -> dict[str, Any]:
        """对最新一次匹配的 benchmark 做比较"""
        bench = self._store.load_latest(task_id=task_id, group=group)
        if bench is None:
            raise ValueError("没有找到匹配的 benchmark")
        return self._compare_from_benchmark(bench)

    def compare_all(self) -> dict[str, Any]:
        """汇总所有 benchmark 结果做整体 skill-level 比较"""
        aggregates = self._store.collect_aggregates()
        if not aggregates:
            raise ValueError("没有找到任何 benchmark 数据")
        all_cases = self._store.collect_cases()
        return self._compare_from_aggregates(
            aggregates, source="all_benchmarks", bench_cases=all_cases,
        )

    def build_comparison_response(
        self,
        benchmark_id: str | None = None,
        baseline_variant: str = BASELINE_VARIANT,
        target_variant: str = TARGET_VARIANT,
    ) -> dict[str, Any]:
        """构建 API contract 用 comparison response"""
        if benchmark_id:
            result = self._compare_from_benchmark(
                self._store.load_benchmark(benchmark_id),
                baseline_variant=baseline_variant,
                target_variant=target_variant,
            )
        else:
            result = self._compare_all_variants(
                baseline_variant=baseline_variant,
                target_variant=target_variant,
            )
        return self.comparison_response_from_result(result)

    def build_skill_summary_contract(self, skill: str) -> dict[str, Any]:
        """构建单个 skill 的 summary contract，未知 skill 返回空态"""
        try:
            result = self.compare_all()
        except ValueError:
            return self.empty_skill_summary(skill)

        comparisons = result.get("comparisons", {})
        by_skill = comparisons.get("by_skill", [])
        by_task = comparisons.get("by_task", [])
        skill_row = next((row for row in by_skill if row.get("skill") == skill), None)
        tasks = [row for row in by_task if row.get("skill") == skill]

        if not skill_row and not tasks:
            return self.empty_skill_summary(skill)

        recent_benchmarks = []
        if hasattr(self._store, "list_recent_benchmarks_for_skill"):
            recent_benchmarks = self._store.list_recent_benchmarks_for_skill(skill)

        summary = {
            "skill": skill,
            "tasks_compared": len(tasks),
            "positive_tasks": len([t for t in tasks if t.get("verdict") == "positive"]),
            "negative_tasks": len([t for t in tasks if t.get("verdict") == "negative"]),
            "neutral_tasks": len([t for t in tasks if t.get("verdict") == "neutral"]),
            "avg_result_score_uplift": skill_row.get("avg_result_score_uplift")
            if skill_row else _r(_avg([
                t.get("result_score_uplift")
                for t in tasks
                if t.get("result_score_uplift") is not None
            ])),
            "avg_normalized_gain": skill_row.get("avg_normalized_gain")
            if skill_row else _r(_avg([
                t.get("normalized_gain")
                for t in tasks
                if t.get("normalized_gain") is not None
            ])),
            "baseline_result_avg": skill_row.get("baseline_result_avg")
            if skill_row else None,
            "target_result_avg": skill_row.get("target_result_avg")
            if skill_row else None,
        }

        return {
            "summary": summary,
            "tasks": tasks,
            "recent_benchmarks": recent_benchmarks,
            "warnings": result.get("warnings", []),
        }

    @staticmethod
    def comparison_response_from_result(result: dict[str, Any]) -> dict[str, Any]:
        comparisons = result.get("comparisons", {})
        return {
            "summary": SkillComparator.summarize_comparison(result),
            "by_skill": comparisons.get("by_skill", []),
            "by_task": comparisons.get("by_task", []),
            "source": result.get("source"),
            "generated_at": result.get("generated_at"),
            "warnings": result.get("warnings", []),
        }

    @staticmethod
    def summarize_comparison(result: dict[str, Any]) -> dict[str, Any]:
        comparisons = result.get("comparisons", {})
        by_task = comparisons.get("by_task", [])
        by_skill = comparisons.get("by_skill", [])
        result_uplifts = [
            row.get("result_score_uplift")
            for row in by_task
            if row.get("result_score_uplift") is not None
        ]
        normalized_gains = [
            row.get("normalized_gain")
            for row in by_task
            if row.get("normalized_gain") is not None
        ]

        return {
            "source": result.get("source", "all_benchmarks"),
            "generated_at": result.get("generated_at"),
            "baseline_variant": result.get("baseline_variant", BASELINE_VARIANT),
            "target_variant": result.get("target_variant", TARGET_VARIANT),
            "tasks_compared": len(by_task),
            "skills_compared": len(by_skill),
            "positive_tasks": len([row for row in by_task if row.get("verdict") == "positive"]),
            "negative_tasks": len([row for row in by_task if row.get("verdict") == "negative"]),
            "neutral_tasks": len([row for row in by_task if row.get("verdict") == "neutral"]),
            "avg_result_score_uplift": _r(_avg(result_uplifts)),
            "avg_normalized_gain": _r(_avg(normalized_gains)),
        }

    @staticmethod
    def empty_comparison_response(source: str = "all_benchmarks") -> dict[str, Any]:
        summary = {
            "source": source,
            "generated_at": None,
            "baseline_variant": BASELINE_VARIANT,
            "target_variant": TARGET_VARIANT,
            "tasks_compared": 0,
            "skills_compared": 0,
            "positive_tasks": 0,
            "negative_tasks": 0,
            "neutral_tasks": 0,
            "avg_result_score_uplift": None,
            "avg_normalized_gain": None,
        }
        return {
            "summary": summary,
            "by_skill": [],
            "by_task": [],
            "source": source,
            "generated_at": None,
            "warnings": [],
        }

    @staticmethod
    def empty_skill_summary(skill: str) -> dict[str, Any]:
        return {
            "summary": {
                "skill": skill,
                "tasks_compared": 0,
                "positive_tasks": 0,
                "negative_tasks": 0,
                "neutral_tasks": 0,
                "avg_result_score_uplift": None,
                "avg_normalized_gain": None,
                "baseline_result_avg": None,
                "target_result_avg": None,
            },
            "tasks": [],
            "recent_benchmarks": [],
            "warnings": [],
        }

    # ── 核心计算 ──────────────────────────────────────────────

    def _compare_from_benchmark(
        self,
        bench: dict,
        baseline_variant: str = BASELINE_VARIANT,
        target_variant: str = TARGET_VARIANT,
    ) -> dict[str, Any]:
        agg_rows = bench.get("aggregates", {}).get("by_task_variant", [])
        benchmark_id = bench["benchmark_id"]
        return self._compare_from_aggregates(
            [{**r, "benchmark_id": benchmark_id} for r in agg_rows],
            source=benchmark_id,
            bench_cases=[{**c, "benchmark_id": benchmark_id}
                         for c in bench.get("cases", [])],
            baseline_variant=baseline_variant,
            target_variant=target_variant,
        )

    def _compare_all_variants(
        self,
        baseline_variant: str = BASELINE_VARIANT,
        target_variant: str = TARGET_VARIANT,
    ) -> dict[str, Any]:
        aggregates = self._store.collect_aggregates()
        if not aggregates:
            raise ValueError("娌℃湁鎵惧埌浠讳綍 benchmark 鏁版嵁")
        all_cases = self._store.collect_cases()
        return self._compare_from_aggregates(
            aggregates,
            source="all_benchmarks",
            bench_cases=all_cases,
            baseline_variant=baseline_variant,
            target_variant=target_variant,
        )

    def _compare_from_aggregates(
        self,
        agg_rows: list[dict],
        source: str,
        bench_cases: list[dict] | None = None,
        baseline_variant: str = BASELINE_VARIANT,
        target_variant: str = TARGET_VARIANT,
    ) -> dict[str, Any]:
        by_task: dict[str, dict[str, dict]] = defaultdict(dict)
        for row in agg_rows:
            tid = row["task_id"]
            vid = row["variant_id"]
            if vid not in by_task[tid]:
                by_task[tid][vid] = row

        skill_map, warnings = self._build_task_skill_map(by_task, bench_cases)

        task_deltas: list[dict[str, Any]] = []
        for tid, variants in sorted(by_task.items()):
            baseline = variants.get(baseline_variant)
            target = variants.get(target_variant)
            if not baseline or not target:
                continue

            skill = skill_map.get(tid)
            delta = self._compute_task_delta(
                tid,
                baseline,
                target,
                skill=skill,
                baseline_variant=baseline_variant,
                target_variant=target_variant,
            )
            task_deltas.append(delta)

        skill_summary = self._compute_skill_summary(task_deltas)

        result: dict[str, Any] = {
            "source": source,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "baseline_variant": baseline_variant,
            "target_variant": target_variant,
            "comparisons": {
                "by_task": task_deltas,
                "by_skill": skill_summary,
            },
        }
        if warnings:
            result["warnings"] = warnings
        return result

    def _compute_task_delta(
        self,
        task_id: str,
        baseline: dict,
        target: dict,
        skill: str | None = None,
        baseline_variant: str = BASELINE_VARIANT,
        target_variant: str = TARGET_VARIANT,
    ) -> dict[str, Any]:
        b_result_score = baseline.get("avg_result_score")
        t_result_score = target.get("avg_result_score")
        b_result_pass = baseline.get("result_pass_rate")
        t_result_pass = target.get("result_pass_rate")
        b_score = baseline.get("avg_weighted_score")
        t_score = target.get("avg_weighted_score")
        b_pass = baseline.get("pass_rate")
        t_pass = target.get("pass_rate")
        b_dur = baseline.get("avg_duration_ms")
        t_dur = target.get("avg_duration_ms")

        result_score_uplift = _safe_diff(t_result_score, b_result_score)
        result_pass_uplift = _safe_diff(t_result_pass, b_result_pass)
        score_uplift = _safe_diff(t_score, b_score)
        pass_uplift = _safe_diff(t_pass, b_pass)
        duration_diff = _safe_diff(t_dur, b_dur)
        verdict_basis = result_score_uplift if result_score_uplift is not None else score_uplift

        # Hake's normalized gain: g = uplift / (1 - baseline)
        normalized_gain = _normalized_gain(result_score_uplift, b_result_score)

        return {
            "task_id": task_id,
            "skill": skill,
            "baseline_variant": baseline_variant,
            "target_variant": target_variant,
            "baseline_result_score": _r(b_result_score),
            "target_result_score": _r(t_result_score),
            "result_score_uplift": _r(result_score_uplift),
            "normalized_gain": _r(normalized_gain),
            "baseline_result_pass_rate": _r(b_result_pass),
            "target_result_pass_rate": _r(t_result_pass),
            "result_pass_rate_uplift": _r(result_pass_uplift),
            "baseline_score": _r(b_score),
            "target_score": _r(t_score),
            "score_uplift": _r(score_uplift),
            "baseline_pass_rate": _r(b_pass),
            "target_pass_rate": _r(t_pass),
            "pass_rate_uplift": _r(pass_uplift),
            "baseline_avg_duration_ms": _r(b_dur),
            "target_avg_duration_ms": _r(t_dur),
            "duration_diff_ms": _r(duration_diff),
            "verdict": _verdict(verdict_basis),
        }

    def _compute_skill_summary(
        self,
        task_deltas: list[dict],
    ) -> list[dict[str, Any]]:
        by_skill: dict[str, list[dict]] = defaultdict(list)
        for d in task_deltas:
            skill = d.get("skill") or "unknown"
            by_skill[skill].append(d)

        summaries: list[dict[str, Any]] = []
        for skill, deltas in sorted(by_skill.items()):
            baseline_result_scores = [
                d["baseline_result_score"]
                for d in deltas
                if d["baseline_result_score"] is not None
            ]
            target_result_scores = [
                d["target_result_score"]
                for d in deltas
                if d["target_result_score"] is not None
            ]
            result_uplifts = [
                d["result_score_uplift"]
                for d in deltas
                if d["result_score_uplift"] is not None
            ]
            norm_gains = [
                d["normalized_gain"]
                for d in deltas
                if d.get("normalized_gain") is not None
            ]
            baseline_scores = [d["baseline_score"] for d in deltas if d["baseline_score"] is not None]
            target_scores = [d["target_score"] for d in deltas if d["target_score"] is not None]
            uplifts = [d["score_uplift"] for d in deltas if d["score_uplift"] is not None]

            positive_tasks = [d["task_id"] for d in deltas if d.get("verdict") == "positive"]
            negative_tasks = [d["task_id"] for d in deltas if d.get("verdict") == "negative"]
            neutral_tasks = [d["task_id"] for d in deltas if d.get("verdict") == "neutral"]

            summaries.append({
                "skill": skill,
                "tasks": len(deltas),
                "baseline_result_avg": _r(_avg(baseline_result_scores)),
                "target_result_avg": _r(_avg(target_result_scores)),
                "avg_result_score_uplift": _r(_avg(result_uplifts)),
                "avg_normalized_gain": _r(_avg(norm_gains)),
                "baseline_avg": _r(_avg(baseline_scores)),
                "skill_avg": _r(_avg(target_scores)),
                "avg_uplift": _r(_avg(uplifts)),
                "positive_tasks": positive_tasks,
                "negative_tasks": negative_tasks,
                "neutral_tasks": neutral_tasks,
            })
        return summaries

    def _build_task_skill_map(
        self,
        by_task: dict[str, dict[str, dict]],
        bench_cases: list[dict] | None,
    ) -> tuple[dict[str, str], list[str]]:
        """构建 task_id -> skill 映射，仅使用 winning benchmark 的运行时快照"""
        warnings: list[str] = []
        skill_map: dict[str, str] = {}

        winning_bid: dict[str, str | None] = {}
        for tid, variants in by_task.items():
            target_row = variants.get(TARGET_VARIANT)
            if target_row and target_row.get("benchmark_id"):
                winning_bid[tid] = target_row.get("benchmark_id")
                continue

            baseline_row = variants.get(BASELINE_VARIANT)
            if baseline_row and baseline_row.get("benchmark_id"):
                winning_bid[tid] = baseline_row.get("benchmark_id")
                continue

            for row in variants.values():
                bid = row.get("benchmark_id")
                if bid:
                    winning_bid[tid] = bid
                    break

        if bench_cases:
            task_all_skills: dict[str, list[str]] = defaultdict(list)
            for case in bench_cases:
                tid = case.get("task_id")
                if not tid:
                    continue
                bid = case.get("benchmark_id")
                expected_bid = winning_bid.get(tid)
                if expected_bid and bid != expected_bid:
                    continue
                for s in case.get("variant", {}).get("enabled_skills", []):
                    if s not in task_all_skills[tid]:
                        task_all_skills[tid].append(s)

            for tid, skills in task_all_skills.items():
                if len(skills) > 1:
                    warnings.append(
                        f"task '{tid}' 关联多个 skill ({', '.join(skills)})，"
                        f"当前仅取首个用于归因"
                    )
                if skills:
                    skill_map[tid] = skills[0]

        if self._task_loader:
            for tid in by_task:
                if tid in skill_map:
                    continue
                try:
                    task = self._task_loader.get_task(tid)
                    skills = task.get("target_skills", [])
                    if len(skills) > 1:
                        warnings.append(
                            f"task '{tid}' 定义了多个 target_skills ({', '.join(skills)})，"
                            f"当前仅取首个用于归因（TaskLoader 兜底）"
                        )
                    if skills:
                        skill_map[tid] = skills[0]
                except Exception:
                    pass

        return skill_map, warnings

    # ── CLI 文本输出 ──────────────────────────────────────────

    @staticmethod
    def format_report(result: dict, use_color: bool = True) -> str:
        lines: list[str] = []
        source = result.get("source", "?")
        bl = result.get("baseline_variant", BASELINE_VARIANT)
        tg = result.get("target_variant", TARGET_VARIANT)

        lines.append(f"═══ Skill Uplift Report ═══")
        lines.append(f"  source: {source}")
        lines.append(f"  比较: {tg} vs {bl}")
        lines.append("")

        warnings = result.get("warnings", [])
        if warnings:
            lines.append("── Warnings ──")
            for warning in warnings:
                lines.append(f"  - {warning}")
            lines.append("")

        task_deltas = result.get("comparisons", {}).get("by_task", [])
        if task_deltas:
            lines.append("── Task-Level Delta ──")
            lines.append(
                f"  {'task_id':<40} {'res_base':>8} {'res_tgt':>8} {'res_up':>8} {'norm_g':>8} {'verdict'}"
            )
            lines.append("  " + "─" * 85)
            for d in task_deltas:
                bs = _fmt(d.get("baseline_result_score"))
                ts = _fmt(d.get("target_result_score"))
                up = _fmt(d.get("result_score_uplift"), signed=True)
                ng = _fmt(d.get("normalized_gain"), signed=True)
                vd = d.get("verdict", "")
                lines.append(f"  {d['task_id']:<40} {bs:>8} {ts:>8} {up:>8} {ng:>8} {vd}")
            lines.append("")

        skill_summary = result.get("comparisons", {}).get("by_skill", [])
        if skill_summary:
            lines.append("── Skill-Level Summary ──")
            for s in skill_summary:
                lines.append(f"  [{s['skill']}]  tasks={s['tasks']}  "
                             f"result_baseline_avg={_fmt(s.get('baseline_result_avg'))}  "
                             f"result_target_avg={_fmt(s.get('target_result_avg'))}  "
                             f"result_avg_uplift={_fmt(s.get('avg_result_score_uplift'), signed=True)}  "
                             f"avg_norm_gain={_fmt(s.get('avg_normalized_gain'), signed=True)}")
                if s.get("positive_tasks"):
                    lines.append(f"    positive: {', '.join(s['positive_tasks'])}")
                if s.get("negative_tasks"):
                    lines.append(f"    negative: {', '.join(s['negative_tasks'])}")
                if s.get("neutral_tasks"):
                    lines.append(f"    neutral:  {', '.join(s['neutral_tasks'])}")
            lines.append("")

        return "\n".join(lines)


# ── 工具函数 ──────────────────────────────────────────────

def _extract_skill_map_from_cases(cases: list[dict]) -> dict[str, str]:
    """从 benchmark cases 的 variant.enabled_skills 提取 task_id → skill 映射（运行时快照）"""
    mapping: dict[str, str] = {}
    for case in cases:
        tid = case.get("task_id")
        if not tid or tid in mapping:
            continue
        variant = case.get("variant", {})
        skills = variant.get("enabled_skills", [])
        if skills:
            mapping[tid] = skills[0]
    return mapping


def _safe_diff(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return a - b


def _normalized_gain(uplift: float | None, baseline: float | None) -> float | None:
    """Hake's normalized gain: g = uplift / (1 - baseline).
    Measures proportional improvement toward perfect score.
    Returns None if inputs are missing or baseline is already 1.0."""
    if uplift is None or baseline is None:
        return None
    headroom = 1.0 - baseline
    if headroom <= 0.0:
        return None
    return uplift / headroom


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _r(v: float | None) -> float | None:
    return round(v, 4) if v is not None else None


def _verdict(uplift: float | None) -> str:
    if uplift is None:
        return "N/A"
    if uplift > 0.01:
        return "positive"
    if uplift < -0.01:
        return "negative"
    return "neutral"


def _fmt(v: float | None, signed: bool = False) -> str:
    if v is None:
        return "N/A"
    if signed:
        return f"{v:+.4f}" if v != 0 else "0.0000"
    return f"{v:.4f}"


# ── CLI 入口 ──────────────────────────────────────────────

def _write_comparison_json(result: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    source = result.get("source", "unknown")
    safe_source = "".join(ch if ch.isalnum() else "_" for ch in source).strip("_")
    path = output_dir / f"comparison_{ts}_{safe_source}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return path


def main():
    parser = argparse.ArgumentParser(
        description="Skill Uplift Comparator — 比较 with_skill vs no_skill"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--benchmark", help="指定 benchmark_id")
    group.add_argument("--latest", action="store_true", help="使用最新一次 benchmark")
    group.add_argument("--all", action="store_true", help="汇总所有 benchmark")

    parser.add_argument("--task", help="过滤 scope.task_id（仅 --latest 时生效）")
    parser.add_argument("--group", help="过滤 scope.group（仅 --latest 时生效）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 到文件")
    parser.add_argument("--workspace", type=Path, default=None, help="自定义 workspace root")

    args = parser.parse_args()

    comparator = SkillComparator(workspace_root=args.workspace)

    try:
        if args.benchmark:
            result = comparator.compare_benchmark(args.benchmark)
        elif args.latest:
            result = comparator.compare_latest(task_id=args.task, group=args.group)
        else:
            result = comparator.compare_all()
    except (KeyError, ValueError) as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    print(SkillComparator.format_report(result))

    if args.json:
        ws = (args.workspace or Config.WORKSPACE_ROOT).resolve()
        output_dir = ws / "evaluations" / "benchmarks" / "comparisons"
        path = _write_comparison_json(result, output_dir)
        print(f"comparison JSON 已写入: {path}")


if __name__ == "__main__":
    main()
