"""
会话相关的工具函数
"""
from pathlib import Path

from .config import Config


def sanitize_session_id(raw: str) -> str:
    """规范化 session_id：只保留字母数字，其余替换为连字符，去除首尾连字符"""
    sanitized = "".join(ch if ch.isascii() and ch.isalnum() else "-" for ch in raw).strip("-")
    return sanitized or "session"


def derive_session_id(log_file: str, explicit: str | None = None) -> str:
    """优先使用显式 session_id，否则根据日志文件名推导"""
    if explicit:
        return sanitize_session_id(explicit)
    stem = Path(log_file).stem or "session"
    return sanitize_session_id(stem)


def ensure_session_dirs(session_id: str, sessions_root: Path | None = None):
    """确保会话相关目录存在，返回 (base, uploads, output, log_file)"""
    if sanitize_session_id(session_id) != session_id:
        raise ValueError(f"Invalid session_id: {session_id!r}")

    root = (sessions_root or Config.SESSIONS_ROOT).resolve()
    base = (root / session_id).resolve()
    if not base.is_relative_to(root):
        raise ValueError(f"Invalid session_id path: {session_id!r}")
    uploads = base / Config.SESSION_UPLOAD_DIR_NAME
    output = base / Config.SESSION_OUTPUT_DIR_NAME
    log_file = base / Config.SESSION_LOG_NAME
    history_file = base / "history.json"
    base.mkdir(parents=True, exist_ok=True)
    uploads.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    if not history_file.exists():
        history_file.write_text("[]", encoding="utf-8")
    return base, uploads, output, log_file

