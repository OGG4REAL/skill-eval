"""
Claude Skills Agent - Docker MCP Server

原子工具基座：Read, Write, List, Bash
通信方式: stdio (标准输入/输出)

变更历史:
- v1.0: run_python + exec_command（初始版本）
- v2.0: 新增 Read/Write/List，冻结 REPL 工具（Phase 1 重构）
- v3.0: 全栈命名统一为 PascalCase（Phase 2）
"""

import sys
import json
import shlex
import subprocess
import traceback
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP


# ============================================================================
# 常量定义
# ============================================================================

WORKSPACE = Path("/workspace")
READONLY_PATHS = [WORKSPACE / "skills"]

# Read 保护
MAX_READ_LINES = 2000           # 默认最大读取行数
MAX_LINE_CHARS = 2000           # 单行最大字符数，超出截断

# Write 保护
MAX_WRITE_SIZE = 1_000_000      # 写入内容上限 1MB

# Bash 输出保护
MAX_OUTPUT_CHARS = 30000        # 输出最大字符数
HEAD_RATIO = 0.8                # 头部保留比例（头尾保留策略）

# List 保护
MAX_LIST_RESULTS = 500          # 目录列表最大返回条目数
ALLOWED_BASH_COMMANDS = {"python", "python3"}
FORBIDDEN_COMMAND_TOKENS = ("\n", "\r", "\x00", ";", "&&", "||", "|", ">", "<", "`", "$(", "&")


# ============================================================================
# 安全辅助函数
# ============================================================================

def _validate_path(path: str) -> Path:
    """
    验证路径安全性，确保在 /workspace 内。

    注意：resolve() 会解析 symlink。如果容器内存在指向 /workspace 外部的 symlink，
    理论上可绕过检查。当前 Docker --network none + skills 只读挂载的隔离度下风险极低。
    """
    target = (WORKSPACE / path).resolve()
    if not target.is_relative_to(WORKSPACE):
        raise ValueError(f"路径必须在 /workspace 内: {path}")
    return target


def _is_readonly(path: Path) -> bool:
    """检查是否为只读区域"""
    return any(path.is_relative_to(ro) for ro in READONLY_PATHS)


def _count_lines(path: Path) -> int:
    """高效统计文件行数（按 1MB 块读取计数换行符，不加载全文到内存）"""
    count = 0
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            count += chunk.count(b'\n')
    # 如果文件非空且最后一个字节不是换行符，额外计一行
    if count == 0:
        # 检查文件是否有内容（空文件返回 0 行）
        if path.stat().st_size > 0:
            count = 1
    else:
        with open(path, 'rb') as f:
            f.seek(-1, 2)  # seek to last byte
            if f.read(1) != b'\n':
                count += 1
    return count


def _truncate_output(text: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    """
    截断输出文本（头尾保留策略）。

    Python 脚本的错误信息和最终结果通常在输出末尾，
    仅保留头部会丢失最关键的信息，因此采用头 80% + 尾 20% 策略。
    """
    if len(text) <= max_chars:
        return text
    head_size = int(max_chars * HEAD_RATIO)
    tail_size = max_chars - head_size
    return (
        text[:head_size]
        + f"\n\n...[输出被截断，共 {len(text)} 字符，保留头部 {head_size} + 尾部 {tail_size} 字符]...\n\n"
        + text[-tail_size:]
    )


def _validate_exec_command(command: str) -> List[str]:
    """Return a safe argv for python script execution."""
    command = command.strip()
    if not command:
        raise ValueError("Empty command")
    if any(token in command for token in FORBIDDEN_COMMAND_TOKENS):
        raise ValueError("Forbidden shell control characters in command")

    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise ValueError(f"Invalid command syntax: {exc}") from exc

    if len(argv) < 2:
        raise ValueError("Command must execute a .py script file")
    if argv[0] not in ALLOWED_BASH_COMMANDS:
        raise ValueError(f"Only python/python3 allowed, got {argv[0]!r}")
    if argv[1] in {"-c", "-m"}:
        raise ValueError("python -c and -m are forbidden")
    if argv[1].startswith("-") or not argv[1].endswith(".py"):
        raise ValueError("Command must execute a .py script file")

    script_path = Path(argv[1])
    target = script_path.resolve() if script_path.is_absolute() else (WORKSPACE / script_path).resolve()
    if not target.is_relative_to(WORKSPACE):
        raise ValueError("Script path must be inside /workspace")

    return [argv[0], str(target), *argv[2:]]


# ============================================================================
# MCP Server
# ============================================================================

mcp = FastMCP("ClaudeSkillsSandbox")


# ============================================================================
# 原子工具：文件操作
# ============================================================================

@mcp.tool(name="Read")
def read_file(
    path: str,
    offset: int = 0,
    limit: int = MAX_READ_LINES,
    encoding: str = "utf-8"
) -> str:
    """
    读取文件内容（带分页和自动截断保护）。

    参数：
        path: 文件路径（相对于 /workspace）
        offset: 起始行号（0-based），用于分页读取大文件
        limit: 最大读取行数，默认 2000 行
        encoding: 文件编码，默认 utf-8

    返回 JSON：
        success, content（带行号）, encoding, lines_read, total_lines, truncated, error
    """
    try:
        target = _validate_path(path)

        if not target.exists():
            return json.dumps({
                "success": False,
                "error": f"文件不存在: {path}"
            }, ensure_ascii=False)

        if not target.is_file():
            return json.dumps({
                "success": False,
                "error": f"不是文件: {path}"
            }, ensure_ascii=False)

        # 编码处理：确定实际可用编码
        actual_encoding = encoding
        try:
            with open(target, 'r', encoding=encoding) as f:
                f.readline()  # 快速试读一行验证编码
        except UnicodeDecodeError:
            if encoding == "utf-8":
                try:
                    with open(target, 'r', encoding='gbk') as f:
                        f.readline()
                    actual_encoding = "gbk"
                except UnicodeDecodeError:
                    return json.dumps({
                        "success": False,
                        "error": "编码识别失败，请尝试指定 encoding 参数（utf-8/gbk/gb18030/latin-1）"
                    }, ensure_ascii=False)
            else:
                return json.dumps({
                    "success": False,
                    "error": f"使用编码 '{encoding}' 解码失败，请检查文件编码"
                }, ensure_ascii=False)

        # 单次 pass 逐行读取：跳过 offset 行 → 收集 limit 行 → 继续计数 total_lines
        # 内存中只保留 limit 行，避免大文件全量加载
        selected = []
        total_lines = 0
        with open(target, 'r', encoding=actual_encoding) as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if offset <= i < offset + limit:
                    selected.append(line)

        lines_read = len(selected)
        truncated = (offset + limit) < total_lines

        # 构建带行号的内容（格式：{line_no:6d}|{line_content}）
        # 单行超过 MAX_LINE_CHARS 时截断
        content_lines = []
        for i, line in enumerate(selected):
            line_no = offset + i + 1  # 1-based 行号
            line = line.rstrip('\n').rstrip('\r')
            if len(line) > MAX_LINE_CHARS:
                line = line[:MAX_LINE_CHARS] + "...[truncated]"
            content_lines.append(f"{line_no:6d}|{line}")

        content = "\n".join(content_lines)

        return json.dumps({
            "success": True,
            "content": content,
            "encoding": actual_encoding,
            "lines_read": lines_read,
            "total_lines": total_lines,
            "truncated": truncated
        }, ensure_ascii=False)

    except ValueError as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"{type(e).__name__}: {e}"
        }, ensure_ascii=False)


@mcp.tool(name="Write")
def write_file(
    path: str,
    content: str,
    encoding: str = "utf-8",
    append: bool = False
) -> str:
    """
    写入文件内容（审计留痕）。

    参数：
        path: 文件路径（相对于 /workspace）
        content: 文件内容
        encoding: 文件编码，默认 utf-8
        append: 是否追加模式，默认覆盖

    安全限制：
        - 禁止写入 /workspace/skills/（只读）
        - 路径必须在 /workspace 内
        - 内容不超过 1MB

    返回 JSON：
        success, path, chars_written, error
    """
    try:
        target = _validate_path(path)

        # 只读区域检查
        if _is_readonly(target):
            return json.dumps({
                "success": False,
                "error": f"禁止写入只读区域: {path}"
            }, ensure_ascii=False)

        # 内容大小检查
        if len(content) > MAX_WRITE_SIZE:
            return json.dumps({
                "success": False,
                "error": f"内容过大（{len(content)} 字符），超过限制（{MAX_WRITE_SIZE} 字符）。请拆分写入。"
            }, ensure_ascii=False)

        # 自动创建父目录
        target.parent.mkdir(parents=True, exist_ok=True)

        # 写入
        mode = 'a' if append else 'w'
        with open(target, mode, encoding=encoding) as f:
            chars_written = f.write(content)

        return json.dumps({
            "success": True,
            "path": str(target.relative_to(WORKSPACE)),
            "chars_written": chars_written
        }, ensure_ascii=False)

    except ValueError as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"{type(e).__name__}: {e}"
        }, ensure_ascii=False)


@mcp.tool(name="List")
def list_files(
    path: str = ".",
    pattern: str = "*",
    recursive: bool = False,
    max_results: int = MAX_LIST_RESULTS
) -> str:
    """
    列出目录内容。

    参数：
        path: 目录路径（相对于 /workspace）
        pattern: 文件名模式（glob 语法，如 *.csv）
        recursive: 是否递归子目录
        max_results: 最大返回条目数，默认 500

    返回 JSON：
        success, files（含 name/type/size）, total_count, truncated, error
    """
    try:
        target = _validate_path(path)

        if not target.exists():
            return json.dumps({
                "success": False,
                "error": f"目录不存在: {path}"
            }, ensure_ascii=False)

        if not target.is_dir():
            return json.dumps({
                "success": False,
                "error": f"不是目录: {path}"
            }, ensure_ascii=False)

        # 收集文件列表
        files: List[Dict[str, Any]] = []

        if recursive:
            entries = sorted(target.rglob(pattern))
        else:
            entries = sorted(target.glob(pattern))

        for entry in entries:
            # 跳过隐藏文件
            if entry.name.startswith('.'):
                continue
            try:
                rel_path = str(entry.relative_to(WORKSPACE))
                file_info: Dict[str, Any] = {
                    "name": rel_path,
                    "type": "dir" if entry.is_dir() else "file",
                }
                if entry.is_file():
                    file_info["size"] = entry.stat().st_size
                files.append(file_info)
            except Exception:
                continue

        total_count = len(files)
        truncated = total_count > max_results

        return json.dumps({
            "success": True,
            "files": files[:max_results],
            "total_count": total_count,
            "truncated": truncated
        }, ensure_ascii=False)

    except ValueError as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"{type(e).__name__}: {e}"
        }, ensure_ascii=False)


# ============================================================================
# 原子工具：命令执行
# ============================================================================

@mcp.tool(name="Bash")
def exec_command(command: str, timeout: int = 30) -> str:
    """
    在 Shell 中执行命令。

    用于：
    - 运行 Python 脚本：python script.py

    参数：
        command: Shell 命令
        timeout: 超时时间（秒）

    返回：
        JSON 格式的执行结果（stdout 超过 30000 字符时自动截断）
    """
    try:
        argv = _validate_exec_command(command)
        result = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(WORKSPACE)
        )

        # 输出截断保护
        stdout = _truncate_output(result.stdout) if result.stdout else ""
        stderr = _truncate_output(result.stderr) if result.stderr else ""

        response = {
            "status": "completed",
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr
        }

    except subprocess.TimeoutExpired:
        response = {
            "status": "timeout",
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds"
        }
    except Exception as e:
        response = {
            "status": "error",
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e)
        }

    return json.dumps(response, ensure_ascii=False, indent=2)


# ============================================================================
# [FROZEN] Python REPL 相关工具 - 当前不暴露给工具层
# 解冻条件：引入 PTC（Programmatic Tool Calling）机制后重新启用 @mcp.tool()
# 包含：run_python, reset_context, get_context_info
# ============================================================================

_GLOBAL_CONTEXT: Dict[str, Any] = {
    "__builtins__": __builtins__,
}
_EXECUTION_COUNT = 0


# @mcp.tool()  # [FROZEN] 审计留痕要求，改用 Write + Bash
def run_python(code: str) -> str:
    """
    在有状态的 Python 环境中执行代码。

    [FROZEN] 当前不暴露。原因：
    - 代码在内存中执行无法留痕，不符合审计要求
    - LLM 倾向于绕过 Skill 自己写代码
    改用 Write + Bash("python temp/xxx.py") 实现审计留痕。
    """
    global _EXECUTION_COUNT, _GLOBAL_CONTEXT
    _EXECUTION_COUNT += 1

    stdout_capture = StringIO()
    stderr_capture = StringIO()
    result_value = None
    error_info = None

    try:
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            try:
                result_value = eval(code, _GLOBAL_CONTEXT)
            except SyntaxError:
                exec(code, _GLOBAL_CONTEXT)
                result_value = None
    except Exception as e:
        error_info = {
            "type": type(e).__name__,
            "message": str(e),
            "traceback": traceback.format_exc()
        }

    response = {
        "success": error_info is None,
        "execution_count": _EXECUTION_COUNT,
        "stdout": stdout_capture.getvalue(),
        "stderr": stderr_capture.getvalue(),
        "result": repr(result_value) if result_value is not None else None,
        "error": error_info
    }

    return json.dumps(response, ensure_ascii=False, indent=2)


# @mcp.tool()  # [FROZEN] 配套 run_python，一并冻结
def reset_context() -> str:
    """重置 Python 执行上下文，清除所有变量。[FROZEN]"""
    global _GLOBAL_CONTEXT, _EXECUTION_COUNT
    _GLOBAL_CONTEXT = {
        "__builtins__": __builtins__,
    }
    _EXECUTION_COUNT = 0
    return json.dumps({"status": "ok", "message": "Context reset successfully"})


# @mcp.tool()  # [FROZEN] 配套 run_python，一并冻结
def get_context_info() -> str:
    """获取当前上下文中的所有变量名及其类型。[FROZEN]"""
    vars_info = {}
    for name, value in _GLOBAL_CONTEXT.items():
        if name.startswith("_") or name == "__builtins__":
            continue
        try:
            repr_str = repr(value)
            if len(repr_str) > 100:
                repr_str = repr_str[:100] + "..."
            vars_info[name] = {
                "type": type(value).__name__,
                "repr": repr_str
            }
        except Exception:
            vars_info[name] = {"type": type(value).__name__, "repr": "<repr failed>"}

    return json.dumps({
        "execution_count": _EXECUTION_COUNT,
        "variables": vars_info
    }, ensure_ascii=False, indent=2)


# ============================================================================
# 启动
# ============================================================================

def _preload_libraries():
    """预加载常用库，减少首次执行延迟"""
    print("[MCP Server] 预加载常用库...", file=sys.stderr)
    try:
        import pandas
        import numpy
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        print("[MCP Server] ✓ 库预加载完成", file=sys.stderr)
    except Exception as e:
        print(f"[MCP Server] 预加载警告: {e}", file=sys.stderr)


if __name__ == "__main__":
    _preload_libraries()
    mcp.run()
