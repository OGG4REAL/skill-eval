import asyncio
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
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

