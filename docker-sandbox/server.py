"""
Claude Skills Agent - Docker MCP Server

有状态的 Python REPL + Bash 命令执行
通信方式: stdio (标准输入/输出)
"""

import sys
import json
import subprocess
import traceback
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from typing import Any, Dict

from mcp.server.fastmcp import FastMCP

# ============================================================================
# 全局状态：Python REPL 上下文（变量跨调用保留）
# ============================================================================

_GLOBAL_CONTEXT: Dict[str, Any] = {
    "__builtins__": __builtins__,
}
_EXECUTION_COUNT = 0

# ============================================================================
# MCP Server
# ============================================================================

mcp = FastMCP("ClaudeSkillsSandbox")

# ============================================================================
# 工具定义
# ============================================================================

@mcp.tool()
def run_python(code: str) -> str:
    """
    在有状态的 Python 环境中执行代码。
    
    特性：
    - 变量在多次调用之间保留（如 Jupyter Kernel）
    - 支持 import，导入的模块会保留
    - 自动捕获 print() 输出和最后一个表达式的值
    
    参数：
        code: 要执行的 Python 代码
        
    返回：
        JSON 格式的执行结果
        
    示例：
        # 第一次调用
        run_python("import pandas as pd; df = pd.read_csv('data.csv')")
        
        # 第二次调用（df 仍然存在）
        run_python("print(df.head())")
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
                # 尝试作为表达式求值
                result_value = eval(code, _GLOBAL_CONTEXT)
            except SyntaxError:
                # 作为语句执行
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


@mcp.tool()
def exec_command(command: str, timeout: int = 30) -> str:
    """
    在 Shell 中执行命令。
    
    用于：
    - 探索文件系统：ls, cat, head, grep 等
    - 安装依赖：pip install xxx
    - 运行脚本：python script.py
    
    参数：
        command: Shell 命令
        timeout: 超时时间（秒）
        
    返回：
        JSON 格式的执行结果
        
    示例：
        exec_command("ls -la /workspace/skills/")
        exec_command("cat /workspace/skills/csv-data-summarizer/SKILL.md")
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd="/workspace"
        )
        
        response = {
            "status": "completed",
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
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


@mcp.tool()
def reset_context() -> str:
    """
    重置 Python 执行上下文，清除所有变量。
    
    用于：
    - 开始新的分析任务
    - 清理内存
    - 解决变量污染问题
    """
    global _GLOBAL_CONTEXT, _EXECUTION_COUNT
    _GLOBAL_CONTEXT = {
        "__builtins__": __builtins__,
    }
    _EXECUTION_COUNT = 0
    return json.dumps({"status": "ok", "message": "Context reset successfully"})


@mcp.tool()
def get_context_info() -> str:
    """
    获取当前上下文中的所有变量名及其类型。
    
    用于调试和规划下一步操作。
    """
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
        except:
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
    import sys
    print("[MCP Server] 预加载常用库...", file=sys.stderr)
    try:
        import pandas
        import numpy
        import matplotlib
        matplotlib.use('Agg')  # 设置非交互后端
        import matplotlib.pyplot as plt
        print("[MCP Server] ✓ 库预加载完成", file=sys.stderr)
    except Exception as e:
        print(f"[MCP Server] 预加载警告: {e}", file=sys.stderr)

if __name__ == "__main__":
    _preload_libraries()
    mcp.run()

