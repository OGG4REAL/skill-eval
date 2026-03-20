"""
评估数据模型
定义 run / trajectory / eval / artifacts / runs_index 的结构
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _generate_run_id() -> str:
    """生成唯一 run_id: run_YYYYMMDD_HHMMSS_<随机6位>"""
    import secrets
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = secrets.token_hex(3)
    return f"run_{ts}_{suffix}"


@dataclass
class TrajectoryEvent:
    """trajectory.jsonl 中的单条事件"""
    type: str
    run_id: str
    timestamp: str = field(default_factory=_now_iso)
    step_index: Optional[int] = None
    iteration: Optional[int] = None
    tool_name: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    duration_ms: Optional[int] = None
    message: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    path: Optional[str] = None
    skills: Optional[List[str]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}


@dataclass
class RunRecord:
    """run.json 主元数据"""
    run_id: str
    session_id: str
    task_id: str = "adhoc"
    variant_id: str = "baseline"
    skills: List[str] = field(default_factory=list)
    trigger: str = "chat"
    user_input: str = ""
    started_at: str = field(default_factory=_now_iso)
    finished_at: Optional[str] = None
    duration_ms: Optional[int] = None
    status: str = "running"  # running / passed / failed
    iterations: int = 0
    tool_calls: int = 0
    tool_errors: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvalRecord:
    """eval.json 评估结果"""
    run_id: str
    task_id: str = "adhoc"
    variant_id: str = "baseline"
    status: str = "passed"
    metrics: Dict[str, Any] = field(default_factory=dict)
    scores: Dict[str, Optional[float]] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ArtifactsRecord:
    """artifacts.json 产物列表"""
    run_id: str
    files: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RunIndexEntry:
    """runs_index.json 中的单条索引"""
    run_id: str
    session_id: str
    task_id: str = "adhoc"
    variant_id: str = "baseline"
    skills: List[str] = field(default_factory=list)
    status: str = "passed"
    score: Optional[float] = None
    duration_ms: Optional[int] = None
    tool_calls: int = 0
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
