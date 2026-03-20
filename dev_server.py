"""
同时启动 FastAPI 后端与前端开发服务器。

使用方法：
    python dev_server.py

按 Ctrl+C 可同时停止两个进程。
"""
from __future__ import annotations

import asyncio
import os
import socket
import sys
from pathlib import Path
from typing import List
import shutil


ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend"
VENV_DIR = ROOT / "venv"
SCRIPTS_DIR = VENV_DIR / ("Scripts" if os.name == "nt" else "bin")
PYTHON_BIN = SCRIPTS_DIR / ("python.exe" if os.name == "nt" else "python")
NPM_EXEC = shutil.which("npm.cmd" if os.name == "nt" else "npm")
ENABLE_BACKEND_RELOAD = os.getenv("DEV_SERVER_RELOAD", "0" if os.name == "nt" else "1") == "1"
BACKEND_HOST = "0.0.0.0"
BACKEND_PORT = 8001

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _ensure_prerequisites() -> None:
    if not PYTHON_BIN.exists():
        raise SystemExit(
            f"未找到虚拟环境解释器：{PYTHON_BIN}\n"
            "请先运行 `python -m venv venv` 并在其中安装依赖。"
        )
    if not FRONTEND_DIR.exists():
        raise SystemExit("未找到 frontend 目录，确认仓库结构是否完整。")
    if NPM_EXEC is None:
        raise SystemExit(
            "未找到 npm，请先安装 Node.js 并确保 npm 在 PATH 中。"
            "如果已安装，可在运行脚本前先打开 Node.js 命令行或将其加入系统环境变量。"
        )


def _is_port_open(host: str, port: int) -> bool:
    target_host = "127.0.0.1" if host == "0.0.0.0" else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((target_host, port)) == 0


async def _wait_for_backend(proc: asyncio.subprocess.Process, host: str, port: int, timeout: float = 10.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if proc.returncode is not None:
            raise RuntimeError(f"后端进程已退出，退出码: {proc.returncode}")
        if _is_port_open(host, port):
            return
        await asyncio.sleep(0.2)
    raise RuntimeError(f"后端在 {timeout:.0f} 秒内未监听 {host}:{port}")


async def _start_process(name: str, cmd: List[str], cwd: Path) -> asyncio.subprocess.Process:
    # 强制设置 Python 的 IO 编码为 utf-8，解决 Windows 下打印 ✓ 等特殊字符崩溃的问题
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout is not None

    async def _stream_output() -> None:
        async for raw_line in proc.stdout:
            # 使用 utf-8 解码输出流
            line = raw_line.decode("utf-8", errors="ignore").rstrip()
            # 在现代终端（如 Cursor/VSCode）中直接打印，避免 gbk 替换导致特殊字符变成问号
            try:
                print(f"[{name}] {line}")
            except UnicodeEncodeError:
                safe_line = line.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
                    sys.stdout.encoding or "utf-8",
                    errors="replace",
                )
                print(f"[{name}] {safe_line}")

    asyncio.create_task(_stream_output())
    return proc


async def _stop_process(name: str, proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return

    print(f"\n[{name}] 终止中...")

    if os.name == "nt":
        # Windows 下 uvicorn / npm 可能会派生子进程，需要按进程树清理。
        killer = await asyncio.create_subprocess_exec(
            "taskkill",
            "/PID",
            str(proc.pid),
            "/T",
            "/F",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        await asyncio.wait_for(killer.communicate(), timeout=10)
        return

    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=10)
    except asyncio.TimeoutError:
        proc.kill()


async def main() -> None:
    _ensure_prerequisites()

    backend_cmd = [
        str(PYTHON_BIN),
        "-m",
        "uvicorn",
        "server.app:app",
        "--host",
        BACKEND_HOST,
        "--port",
        str(BACKEND_PORT),
    ]
    if ENABLE_BACKEND_RELOAD:
        backend_cmd.extend([
            "--reload",
            "--reload-dir",
            "server",
            "--reload-dir",
            "agent_system",
        ])
    frontend_cmd = [NPM_EXEC, "run", "dev", "--", "--host", "0.0.0.0"]

    print("启动 FastAPI + Vite 开发环境，按 Ctrl+C 结束。\n")
    if not ENABLE_BACKEND_RELOAD:
        print(f"[backend] 已关闭 reload，避免 Windows 下残留子进程占用 {BACKEND_PORT}。\n")

    if _is_port_open(BACKEND_HOST, BACKEND_PORT):
        raise SystemExit(
            f"后端端口 {BACKEND_PORT} 已被占用，请先释放旧进程后再启动。"
        )

    backend_proc = await _start_process("backend", backend_cmd, ROOT)
    try:
        await _wait_for_backend(backend_proc, BACKEND_HOST, BACKEND_PORT)
    except Exception:
        await _stop_process("backend", backend_proc)
        raise

    frontend_proc = await _start_process("frontend", frontend_cmd, FRONTEND_DIR)

    try:
        # 等待任一进程结束
        await asyncio.wait(
            [asyncio.create_task(backend_proc.wait()), asyncio.create_task(frontend_proc.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        for name, proc in [("backend", backend_proc), ("frontend", frontend_proc)]:
            await _stop_process(name, proc)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n收到中断信号，正在清理进程...")

