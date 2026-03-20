"""
RunsRegistry
维护 evaluations/runs_index.json 跨会话索引
以及 evaluations/tasks/*.json 本地任务定义
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import EvalRecord, RunIndexEntry, RunRecord

_index_lock = threading.Lock()


class RunsRegistry:
    """跨会话 run 索引管理器"""

    def __init__(self, evaluations_dir: Path):
        self._eval_dir = evaluations_dir
        self._eval_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._eval_dir / "runs_index.json"
        self._tasks_dir = self._eval_dir / "tasks"
        self._tasks_dir.mkdir(parents=True, exist_ok=True)

    def append_run(self, run: RunRecord, eval_record: Optional[EvalRecord] = None) -> None:
        """追加一条 run 到全局索引（线程安全）"""
        with _index_lock:
            index = self._load_index()

            avg_score: Optional[float] = None
            if eval_record and eval_record.scores:
                valid = [v for v in eval_record.scores.values() if v is not None]
                if valid:
                    avg_score = round(sum(valid) / len(valid), 2)

            entry = RunIndexEntry(
                run_id=run.run_id,
                session_id=run.session_id,
                task_id=run.task_id,
                variant_id=run.variant_id,
                skills=run.skills,
                status=run.status,
                score=avg_score,
                duration_ms=run.duration_ms,
                tool_calls=run.tool_calls,
                created_at=run.finished_at or run.started_at,
            )

            index.append(entry.to_dict())

            if len(index) > 200:
                index = index[-200:]

            self._save_index(index)

    def list_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """返回最近 N 条 run 索引"""
        index = self._load_index()
        return list(reversed(index[-limit:]))

    def list_tasks(self) -> List[Dict[str, Any]]:
        """读取本地任务定义列表"""
        tasks = []
        if not self._tasks_dir.exists():
            return tasks
        for f in sorted(self._tasks_dir.glob("*.json")):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    tasks.append(json.load(fh))
            except Exception:
                continue
        return tasks

    def match_task_id(self, user_input: str) -> str:
        """
        简单匹配用户输入到 task_id。
        匹配不到返回 'adhoc'。
        """
        tasks = self.list_tasks()
        lower_input = user_input.lower()
        for task in tasks:
            patterns = task.get("input_patterns", [])
            for pattern in patterns:
                if pattern.lower() in lower_input:
                    return task.get("task_id", "adhoc")
        return "adhoc"

    def _load_index(self) -> List[Dict[str, Any]]:
        if not self._index_path.exists():
            return []
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_index(self, index: List[Dict[str, Any]]) -> None:
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._eval_dir), suffix=".tmp", prefix="runs_index_"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(index, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, str(self._index_path))
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            print(f"[RunsRegistry] 保存 runs_index.json 失败: {e}")
