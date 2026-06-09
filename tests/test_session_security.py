from pathlib import Path

import pytest

from agent_system.session import ensure_session_dirs


def test_ensure_session_dirs_rejects_traversal(tmp_path: Path):
    with pytest.raises(ValueError):
        ensure_session_dirs("../escape", sessions_root=tmp_path)


def test_ensure_session_dirs_rejects_unsanitized_id(tmp_path: Path):
    with pytest.raises(ValueError):
        ensure_session_dirs("bad/id", sessions_root=tmp_path)


def test_ensure_session_dirs_rejects_non_ascii_id(tmp_path: Path):
    with pytest.raises(ValueError):
        ensure_session_dirs("会话", sessions_root=tmp_path)


def test_ensure_session_dirs_stays_inside_root(tmp_path: Path):
    base, uploads, output, log_file = ensure_session_dirs("safe-session", sessions_root=tmp_path)

    assert base.is_relative_to(tmp_path)
    assert uploads == base / "uploads"
    assert output == base / "output"
    assert log_file == base / "chat.log"
