"""
Evaluation 模块
提供 run / trajectory / eval 数据落盘与规则评分能力
"""
from __future__ import annotations

from .models import RunRecord, TrajectoryEvent, EvalRecord, ArtifactsRecord, RunIndexEntry
from .recorder import RunRecorder
from .scorer import RuleScorer
from .registry import RunsRegistry
from .task_loader import TaskLoader, TaskLoadError
from .variant_manager import VariantManager, VariantResolutionError
from .benchmark_store import BenchmarkStore

__all__ = [
    "RunRecord",
    "TrajectoryEvent",
    "EvalRecord",
    "ArtifactsRecord",
    "RunIndexEntry",
    "RunRecorder",
    "RuleScorer",
    "RunsRegistry",
    "TaskLoader",
    "TaskLoadError",
    "VariantManager",
    "VariantResolutionError",
    "BenchmarkStore",
    "SkillComparator",
]


def __getattr__(name: str):
    """延迟导入 CLI 模块，避免 `python -m` 时的 runpy RuntimeWarning。"""
    if name == "SkillComparator":
        from .skill_comparator import SkillComparator

        return SkillComparator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
