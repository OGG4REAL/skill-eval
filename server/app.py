import asyncio
import mimetypes
import os
import posixpath
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import List, Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from agent_system.config import Config
from agent_system.session import ensure_session_dirs
from server.copilot_adapter import create_copilot_router, get_copilot_backend


app = FastAPI(title="CSV Agent Server", version="2.0.0")

# 挂载 CopilotKit 路由 (Phase 2)
copilot_router = create_copilot_router(get_copilot_backend())
app.include_router(copilot_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（开发环境）
    allow_credentials=False,  # 使用通配符时不能开启 credentials
    allow_methods=["*"],
    allow_headers=["*"],
)


class SessionCreateRequest(BaseModel):
    session_id: Optional[str] = None


class MessageRequest(BaseModel):
    query: str
    max_iterations: Optional[int] = None


class WorkspaceNode(BaseModel):
    path: str
    name: str
    kind: Literal["file", "directory"]
    size: Optional[int] = None
    modified: Optional[str] = None
    readonly: bool = False
    children: Optional[List["WorkspaceNode"]] = None


class WorkspaceTreeResponse(BaseModel):
    session_id: str
    roots: List[WorkspaceNode]


class WorkspaceFileResponse(BaseModel):
    path: str
    name: str
    size: int
    modified: str
    readonly: bool = False
    content: str
    language: Optional[str] = None
    mime_type: str = "text/plain"
    truncated: bool = False


WorkspaceNode.model_rebuild()


@dataclass(frozen=True)
class WorkspaceRoot:
    logical_path: str
    actual_path: Path
    readonly: bool
    kind: Literal["file", "directory"]


def _get_session_dirs(session_id: str):
    base, uploads, output, log_file = ensure_session_dirs(session_id)
    return {
        "base": base,
        "uploads": uploads,
        "output": output,
        "log": log_file,
    }


def _list_files(directory: Path):
    files = []
    for path in sorted(directory.iterdir()):
        if path.is_file():
            stat = path.stat()
            files.append({
                "name": path.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
    return files


def _to_iso_timestamp(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat()


def _guess_language(path: Path) -> Optional[str]:
    extension_map = {
        ".md": "markdown",
        ".markdown": "markdown",
        ".json": "json",
        ".py": "python",
        ".txt": "text",
        ".log": "text",
        ".csv": "csv",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".sh": "shell",
    }
    return extension_map.get(path.suffix.lower())


def _is_text_file(path: Path) -> bool:
    mime_type, _ = mimetypes.guess_type(path.name)
    if mime_type:
        return mime_type.startswith("text/") or mime_type in {
            "application/json",
            "application/xml",
            "application/javascript",
        }
    return path.suffix.lower() in {
        ".md",
        ".markdown",
        ".json",
        ".py",
        ".txt",
        ".log",
        ".csv",
        ".yaml",
        ".yml",
        ".sh",
        ".sql",
    }


def _get_workspace_roots(session_id: str) -> List[WorkspaceRoot]:
    dirs = _get_session_dirs(session_id)
    base_dir = dirs["base"]
    return [
        WorkspaceRoot(
            logical_path="/workspace/uploads",
            actual_path=dirs["uploads"],
            readonly=False,
            kind="directory",
        ),
        WorkspaceRoot(
            logical_path="/workspace/output",
            actual_path=dirs["output"],
            readonly=False,
            kind="directory",
        ),
        WorkspaceRoot(
            logical_path="/workspace/temp",
            actual_path=base_dir / "temp",
            readonly=False,
            kind="directory",
        ),
        WorkspaceRoot(
            logical_path=f"/workspace/{Config.TOOL_RESULTS_DIR_NAME}",
            actual_path=base_dir / Config.TOOL_RESULTS_DIR_NAME,
            readonly=False,
            kind="directory",
        ),
        WorkspaceRoot(
            logical_path="/workspace/chat.log",
            actual_path=dirs["log"],
            readonly=False,
            kind="file",
        ),
        WorkspaceRoot(
            logical_path="/workspace/history.json",
            actual_path=base_dir / "history.json",
            readonly=False,
            kind="file",
        ),
        WorkspaceRoot(
            logical_path="/workspace/skills",
            actual_path=Config.SKILLS_DIR,
            readonly=True,
            kind="directory",
        ),
    ]


def _normalize_workspace_path(path: str) -> str:
    normalized = posixpath.normpath(path or "")
    if normalized != "/workspace" and not normalized.startswith("/workspace/"):
        raise HTTPException(status_code=400, detail="path 必须位于 /workspace 下")
    return normalized


def _resolve_workspace_path(session_id: str, logical_path: str) -> tuple[WorkspaceRoot, Path]:
    normalized = _normalize_workspace_path(logical_path)
    requested = PurePosixPath(normalized)

    for root in sorted(_get_workspace_roots(session_id), key=lambda item: len(item.logical_path), reverse=True):
        root_path = PurePosixPath(root.logical_path)
        if root.kind == "file":
            if requested == root_path:
                return root, root.actual_path
            continue

        if requested != root_path and root_path not in requested.parents:
            continue

        relative_parts = requested.relative_to(root_path).parts
        actual_path = root.actual_path.joinpath(*relative_parts) if relative_parts else root.actual_path
        actual_root = root.actual_path.resolve()
        resolved_target = actual_path.resolve()
        if not resolved_target.is_relative_to(actual_root):
            raise HTTPException(status_code=400, detail="非法 workspace 路径")
        return root, actual_path

    raise HTTPException(status_code=404, detail="workspace 路径不存在")


def _serialize_workspace_node(
    *,
    logical_path: str,
    actual_path: Path,
    readonly: bool,
    kind: Literal["file", "directory"],
) -> WorkspaceNode:
    if kind == "file":
        size = actual_path.stat().st_size if actual_path.exists() and actual_path.is_file() else None
        return WorkspaceNode(
            path=logical_path,
            name=PurePosixPath(logical_path).name,
            kind="file",
            size=size,
            modified=_to_iso_timestamp(actual_path),
            readonly=readonly,
            children=None,
        )

    children: List[WorkspaceNode] = []
    if actual_path.exists() and actual_path.is_dir():
        entries = sorted(
            actual_path.iterdir(),
            key=lambda item: (item.is_file(), item.name.lower()),
        )
        for child in entries:
            child_logical_path = f"{logical_path}/{child.name}"
            child_kind: Literal["file", "directory"] = "directory" if child.is_dir() else "file"
            children.append(
                _serialize_workspace_node(
                    logical_path=child_logical_path,
                    actual_path=child,
                    readonly=readonly,
                    kind=child_kind,
                )
            )

    return WorkspaceNode(
        path=logical_path,
        name=PurePosixPath(logical_path).name,
        kind="directory",
        modified=_to_iso_timestamp(actual_path),
        readonly=readonly,
        children=children,
    )


@app.post("/sessions")
def create_session(payload: SessionCreateRequest):
    session_id = payload.session_id or uuid4().hex
    dirs = _get_session_dirs(session_id)
    return {
        "session_id": session_id,
        "base": str(dirs["base"]),
        "uploads": str(dirs["uploads"]),
        "output": str(dirs["output"]),
        "log": str(dirs["log"]),
    }


@app.get("/sessions")
def list_sessions():
    sessions = []
    for path in sorted(Config.SESSIONS_ROOT.iterdir()):
        if path.is_dir():
            sessions.append({
                "session_id": path.name,
                "base": str(path),
                "uploads": str(path / Config.SESSION_UPLOAD_DIR_NAME),
                "output": str(path / Config.SESSION_OUTPUT_DIR_NAME)
            })
    return sessions


@app.get("/sessions/{session_id}/workspace", response_model=WorkspaceTreeResponse)
def get_workspace_tree(session_id: str):
    roots = [
        _serialize_workspace_node(
            logical_path=root.logical_path,
            actual_path=root.actual_path,
            readonly=root.readonly,
            kind=root.kind,
        )
        for root in _get_workspace_roots(session_id)
    ]
    return WorkspaceTreeResponse(session_id=session_id, roots=roots)


@app.get("/sessions/{session_id}/workspace/file", response_model=WorkspaceFileResponse)
def get_workspace_file(session_id: str, path: str = Query(..., description="逻辑 /workspace 路径")):
    root, actual_path = _resolve_workspace_path(session_id, path)
    if not actual_path.exists() or not actual_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    if not _is_text_file(actual_path):
        raise HTTPException(status_code=415, detail="暂不支持预览二进制文件")

    try:
        content = actual_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = actual_path.read_text(encoding="utf-8", errors="replace")

    mime_type = mimetypes.guess_type(actual_path.name)[0] or "text/plain"
    return WorkspaceFileResponse(
        path=_normalize_workspace_path(path),
        name=actual_path.name,
        size=actual_path.stat().st_size,
        modified=datetime.fromtimestamp(actual_path.stat().st_mtime).isoformat(),
        readonly=root.readonly,
        content=content,
        language=_guess_language(actual_path),
        mime_type=mime_type,
        truncated=False,
    )


@app.post("/sessions/{session_id}/files")
async def upload_files(session_id: str, files: List[UploadFile] = File(...)):
    dirs = _get_session_dirs(session_id)
    saved_files = []
    for upload in files:
        destination = dirs["uploads"] / upload.filename
        with destination.open("wb") as buffer:
            shutil.copyfileobj(upload.file, buffer)
        saved_files.append(upload.filename)
    return {"uploaded": saved_files}


@app.get("/sessions/{session_id}/files")
def list_uploaded_files(session_id: str):
    dirs = _get_session_dirs(session_id)
    return _list_files(dirs["uploads"])


@app.get("/sessions/{session_id}/files/{filename}")
def download_uploaded_file(session_id: str, filename: str):
    dirs = _get_session_dirs(session_id)
    file_path = dirs["uploads"] / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(file_path)


@app.delete("/sessions/{session_id}/files/{filename}")
def delete_uploaded_file(session_id: str, filename: str):
    dirs = _get_session_dirs(session_id)
    file_path = dirs["uploads"] / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    file_path.unlink()
    return {"deleted": filename}


@app.post("/sessions/{session_id}/messages")
def run_agent_message(session_id: str, payload: MessageRequest):
    dirs = _get_session_dirs(session_id)
    if not payload.query:
        raise HTTPException(status_code=400, detail="query 不能为空")
    
    cmd = [
        sys.executable,
        "-m",
        "agent_system.main",
        payload.query,
        "--session-id",
        session_id,
        "--log",
        str(dirs["log"]),
        "--no-welcome",
    ]
    if payload.max_iterations:
        cmd.extend(["--max-iterations", str(payload.max_iterations)])
    
    # 异步启动 Agent，将 stdout/stderr 重定向到日志文件
    # 这样 SSE 接口可以实时读取到日志
    log_file = open(dirs["log"], "a", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"  # 强制 UTF-8 输出，避免 Windows 下的 GBK 问题

    subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
    )

    return {
        "status": "started",
        "log": str(dirs["log"]),
    }


@app.get("/sessions/{session_id}/stream")
async def stream_session_log(session_id: str):
    dirs = _get_session_dirs(session_id)
    log_path = dirs["log"]
    log_path.touch(exist_ok=True)

    async def log_reader():
        with log_path.open("r", encoding="utf-8", errors="ignore") as log_file:
            log_file.seek(0, os.SEEK_END)
            while True:
                line = log_file.readline()
                if line:
                    yield f"data: {line.rstrip()}\n\n"
                else:
                    await asyncio.sleep(0.5)

    return StreamingResponse(log_reader(), media_type="text/event-stream")


@app.get("/sessions/{session_id}/outputs")
def list_outputs(session_id: str):
    dirs = _get_session_dirs(session_id)
    return _list_files(dirs["output"])


@app.get("/sessions/{session_id}/outputs/{filename}")
def download_output_file(session_id: str, filename: str):
    dirs = _get_session_dirs(session_id)
    file_path = dirs["output"] / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(file_path)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server.app:app", host="0.0.0.0", port=8000, reload=True)

