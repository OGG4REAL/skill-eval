"""
同时启动 FastAPI 后端与前端开发服务器。

使用方法：
    python dev_server.py

按 Ctrl+C 可同时停止两个进程。
"""
from __future__ import annotations

import asyncio
import os
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
            print(f"[{name}] {line}")

    asyncio.create_task(_stream_output())
    return proc


async def main() -> None:
    _ensure_prerequisites()

    backend_cmd = [
        str(PYTHON_BIN),
        "-m",
        "uvicorn",
        "server.app:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--reload",
    ]
    frontend_cmd = [NPM_EXEC, "run", "dev", "--", "--host", "0.0.0.0"]

    print("启动 FastAPI + Vite 开发环境，按 Ctrl+C 结束。\n")

    backend_proc = await _start_process("backend", backend_cmd, ROOT)
    frontend_proc = await _start_process("frontend", frontend_cmd, FRONTEND_DIR)

    try:
        # 等待任一进程结束
        await asyncio.wait(
            [asyncio.create_task(backend_proc.wait()), asyncio.create_task(frontend_proc.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        for name, proc in [("backend", backend_proc), ("frontend", frontend_proc)]:
            if proc.returncode is None:
                proc.terminate()
                print(f"\n[{name}] 终止中...")
                try:
                    await asyncio.wait_for(proc.wait(), timeout=10)
                except asyncio.TimeoutError:
                    proc.kill()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n收到中断信号，正在清理进程...")

