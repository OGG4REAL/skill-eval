"""
RuleScorer
Phase 1 最小规则评分器

四个评分项：
- task_success: 是否成功完成
- tool_efficiency: 工具调用效率
- artifact_completeness: 产物完整性
- trajectory_quality: 轨迹质量启发式
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .models import EvalRecord, RunRecord


class RuleScorer:
    """基于规则的最小评分器"""

    def score(self, run: RunRecord, artifacts: List[str]) -> EvalRecord:
        """
        对一次 run 生成评估结果。
        评分失败不影响主流程——异常时返回降级结果。
        """
        try:
            scores = {
                "task_success": self._score_task_success(run),
                "tool_efficiency": self._score_tool_efficiency(run),
                "artifact_completeness": self._score_artifact_completeness(run, artifacts),
                "trajectory_quality": self._score_trajectory_quality(run),
            }
            metrics = {
                "duration_ms": run.duration_ms,
                "iterations": run.iterations,
                "tool_calls": run.tool_calls,
                "tool_errors": run.tool_errors,
                "files_generated": len(artifacts),
            }
            notes: List[str] = []
            if run.tool_errors > 0:
                notes.append(f"存在 {run.tool_errors} 次工具调用失败")
            if run.iterations >= 10:
                notes.append(f"迭代次数较多: {run.iterations}")

            return EvalRecord(
                run_id=run.run_id,
                task_id=run.task_id,
                variant_id=run.variant_id,
                status=run.status,
                metrics=metrics,
                scores=scores,
                notes=notes,
            )
        except Exception as e:
            return EvalRecord(
                run_id=run.run_id,
                task_id=run.task_id,
                variant_id=run.variant_id,
                status=run.status,
                metrics={},
                scores={
                    "task_success": None,
                    "tool_efficiency": None,
                    "artifact_completeness": None,
                    "trajectory_quality": None,
                },
                notes=[f"评分异常: {e}"],
            )

    def _score_task_success(self, run: RunRecord) -> int:
        if run.status == "passed":
            return 1
        return 0

    def _score_tool_efficiency(self, run: RunRecord) -> float:
        if run.tool_calls == 0:
            return 1.0
        base = 1.0
        base -= 0.15 * run.tool_errors
        extra = max(0, run.tool_calls - run.iterations * 3)
        base -= 0.05 * extra
        return round(max(0.0, min(1.0, base)), 2)

    def _score_artifact_completeness(self, run: RunRecord, artifacts: List[str]) -> Optional[float]:
        if run.task_id == "adhoc":
            if len(artifacts) > 0:
                return 1.0
            return None
        return 1.0 if len(artifacts) > 0 else 0.0

    def _score_trajectory_quality(self, run: RunRecord) -> float:
        score = 1.0
        if run.status != "passed":
            score -= 0.3
        if run.tool_errors > 0:
            score -= min(0.3, 0.1 * run.tool_errors)
        if run.iterations > 15:
            score -= 0.2
        elif run.iterations > 10:
            score -= 0.1
        return round(max(0.0, min(1.0, score)), 2)
