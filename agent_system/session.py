"""
会话相关的工具函数
"""
from pathlib import Path

from .config import Config


def _sanitize_session_id(raw: str) -> str:
    sanitized = "".join(ch if ch.isalnum() else "-" for ch in raw).strip("-")
    return sanitized or "session"


def derive_session_id(log_file: str, explicit: str | None = None) -> str:
    """优先使用显式 session_id，否则根据日志文件名推导"""
    if explicit:
        return _sanitize_session_id(explicit)
    stem = Path(log_file).stem or "session"
    return _sanitize_session_id(stem)


def ensure_session_dirs(session_id: str):
    """确保会话相关目录存在，返回 (base, uploads, output, log_file)"""
    base = Config.SESSIONS_ROOT / session_id
    uploads = base / Config.SESSION_UPLOAD_DIR_NAME
    output = base / Config.SESSION_OUTPUT_DIR_NAME
    log_file = base / Config.SESSION_LOG_NAME
    base.mkdir(parents=True, exist_ok=True)
    uploads.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    return base, uploads, output, log_file

