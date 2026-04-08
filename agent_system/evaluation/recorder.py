"""
RunRecorder
负责 run 生命周期内事件的结构化记录与落盘

核心职责：
- 管理 run 目录 (sessions/{session_id}/runs/{run_id}/)
- 实时追加 trajectory.jsonl
- run 结束时生成 run.json / eval.json / artifacts.json
"""
from __future__ import annotations

import json
import posixpath
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import (
    ArtifactsRecord,
    EvalRecord,
    RunRecord,
    TrajectoryEvent,
    _generate_run_id,
    _now_iso,
)


class RunRecorder:
    """单次 run 的记录器，一个 run 对应一个 RunRecorder 实例"""

    def __init__(self, session_id: str, sessions_root: Path, user_input: str = ""):
        self.session_id = session_id
        self.run_id = _generate_run_id()

        self._run_dir = sessions_root / session_id / "runs" / self.run_id
        self._run_dir.mkdir(parents=True, exist_ok=True)

        self._trajectory_path = self._run_dir / "trajectory.jsonl"
        self._trajectory_file = open(self._trajectory_path, "a", encoding="utf-8")

        self._step_index = 0
        self._current_iteration = 0
        self._start_time = time.time()
        self._tool_calls = 0
        self._tool_errors = 0
        self._artifacts: List[str] = []
        self._injected_skills: List[str] = []
        self._has_final_response = False

        self.run_record = RunRecord(
            run_id=self.run_id,
            session_id=session_id,
            user_input=user_input,
        )

        self._emit(TrajectoryEvent(
            type="run_started",
            run_id=self.run_id,
        ))

    @property
    def tool_calls_count(self) -> int:
        return self._tool_calls

    @property
    def tool_errors_count(self) -> int:
        return self._tool_errors

    @property
    def artifacts_list(self) -> List[str]:
        return list(self._artifacts)

    def _next_step(self) -> int:
        self._step_index += 1
        return self._step_index

    @staticmethod
    def _normalize_workspace_path(path: str) -> str:
        """统一日志中的工作区路径口径，优先使用逻辑 /workspace/... 形式。"""
        if not isinstance(path, str) or not path:
            return path

        normalized = path.replace("\\", "/")
        if normalized == "/workspace":
            return normalized
        if normalized.startswith("/workspace/"):
            return posixpath.normpath(normalized)
        if normalized.startswith("/"):
            return normalized

        normalized = normalized.lstrip("./")
        return posixpath.normpath(f"/workspace/{normalized}")

    def _emit(self, event: TrajectoryEvent) -> None:
        try:
            line = json.dumps(event.to_dict(), ensure_ascii=False)
            self._trajectory_file.write(line + "\n")
            self._trajectory_file.flush()
        except Exception as e:
            print(f"[RunRecorder] trajectory 写入失败: {e}")

    def record_iteration_start(self, iteration: int) -> None:
        self._current_iteration = iteration
        self._emit(TrajectoryEvent(
            type="iteration_started",
            run_id=self.run_id,
            step_index=self._next_step(),
            iteration=iteration,
        ))

    def record_thinking(self, message: str) -> None:
        self._emit(TrajectoryEvent(
            type="thinking",
            run_id=self.run_id,
            step_index=self._next_step(),
            iteration=self._current_iteration,
            message=message[:500] if message else "",
        ))

    def record_llm_call_start(self) -> float:
        self._emit(TrajectoryEvent(
            type="llm_call_started",
            run_id=self.run_id,
            step_index=self._next_step(),
            iteration=self._current_iteration,
        ))
        return time.time()

    def record_llm_call_finish(
        self,
        start_time: float,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        usage: Optional[Dict[str, Any]] = None,
    ) -> None:
        duration_ms = int((time.time() - start_time) * 1000)
        self._emit(TrajectoryEvent(
            type="llm_call_finished",
            run_id=self.run_id,
            step_index=self._next_step(),
            iteration=self._current_iteration,
            duration_ms=duration_ms,
            model=model,
            provider=provider,
            usage=usage,
        ))

    def record_tool_call_start(self, tool_name: str, arguments: Dict[str, Any]) -> float:
        self._tool_calls += 1
        safe_args = {}
        for k, v in arguments.items():
            if k == "path" and isinstance(v, str):
                v = self._normalize_workspace_path(v)
            s = str(v)
            safe_args[k] = s[:200] if len(s) > 200 else v
        self._emit(TrajectoryEvent(
            type="tool_call_started",
            run_id=self.run_id,
            step_index=self._next_step(),
            iteration=self._current_iteration,
            tool_name=tool_name,
            arguments=safe_args,
        ))
        return time.time()

    def record_tool_call_finish(
        self,
        tool_name: str,
        start_time: float,
        status: str = "success",
        error: Optional[str] = None,
    ) -> None:
        duration_ms = int((time.time() - start_time) * 1000)
        if status != "success":
            self._tool_errors += 1
        self._emit(TrajectoryEvent(
            type="tool_call_finished",
            run_id=self.run_id,
            step_index=self._next_step(),
            iteration=self._current_iteration,
            tool_name=tool_name,
            status=status,
            duration_ms=duration_ms,
            error=error[:300] if error else None,
        ))

    def record_skill_injected(self, skill_name: str) -> None:
        if skill_name not in self._injected_skills:
            self._injected_skills.append(skill_name)
        self._emit(TrajectoryEvent(
            type="skill_injected",
            run_id=self.run_id,
            step_index=self._next_step(),
            iteration=self._current_iteration,
            skills=[skill_name],
        ))

    def record_artifact_created(self, path: str) -> None:
        path = self._normalize_workspace_path(path)
        if path not in self._artifacts:
            self._artifacts.append(path)
        self._emit(TrajectoryEvent(
            type="artifact_created",
            run_id=self.run_id,
            step_index=self._next_step(),
            iteration=self._current_iteration,
            path=path,
        ))

    def record_client_tool(self, tool_name: str, arguments: Dict[str, Any]) -> None:
        self._emit(TrajectoryEvent(
            type="client_tool_emitted",
            run_id=self.run_id,
            step_index=self._next_step(),
            iteration=self._current_iteration,
            tool_name=tool_name,
            arguments=arguments,
        ))

    def mark_final_response(self) -> None:
        self._has_final_response = True

    def finalize(
        self,
        status: str = "passed",
        iterations: int = 0,
        eval_record: Optional[EvalRecord] = None,
    ) -> RunRecord:
        """
        结束 run，写入 run.json / eval.json / artifacts.json。
        返回完成的 RunRecord。
        """
        finished_at = _now_iso()
        duration_ms = int((time.time() - self._start_time) * 1000)

        self._emit(TrajectoryEvent(
            type="run_completed" if status == "passed" else "run_failed",
            run_id=self.run_id,
            status=status,
            duration_ms=duration_ms,
        ))

        try:
            self._trajectory_file.close()
        except Exception:
            pass

        self.run_record.finished_at = finished_at
        self.run_record.duration_ms = duration_ms
        self.run_record.status = status
        self.run_record.iterations = iterations
        self.run_record.tool_calls = self._tool_calls
        self.run_record.tool_errors = self._tool_errors
        self.run_record.skills = self._injected_skills

        self._write_json("run.json", self.run_record.to_dict())

        for evidence in ["/workspace/chat.log", "/workspace/history.json"]:
            if evidence not in self._artifacts:
                self._artifacts.append(evidence)

        artifacts = ArtifactsRecord(run_id=self.run_id, files=self._artifacts)
        self._write_json("artifacts.json", artifacts.to_dict())

        if eval_record:
            self._write_json("eval.json", eval_record.to_dict())

        return self.run_record

    def _write_json(self, filename: str, data: Dict[str, Any]) -> None:
        try:
            path = self._run_dir / filename
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[RunRecorder] 写入 {filename} 失败: {e}")

    @property
    def has_final_response(self) -> bool:
        return self._has_final_response
