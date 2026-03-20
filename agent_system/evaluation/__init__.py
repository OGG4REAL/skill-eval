"""
Evaluation 模块
提供 run / trajectory / eval 数据落盘与规则评分能力
"""
from .models import RunRecord, TrajectoryEvent, EvalRecord, ArtifactsRecord, RunIndexEntry
from .recorder import RunRecorder
from .scorer import RuleScorer
from .registry import RunsRegistry

__all__ = [
    "RunRecord",
    "TrajectoryEvent",
    "EvalRecord",
    "ArtifactsRecord",
    "RunIndexEntry",
    "RunRecorder",
    "RuleScorer",
    "RunsRegistry",
]
