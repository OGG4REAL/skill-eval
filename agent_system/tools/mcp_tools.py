"""
MCP 工具模块 - 通过 stdio 与 Docker 容器内的 MCP Server 通信

包含：
- MCPClient: MCP 协议通信
- MCPToolBase: Read/Write/List 公共基类
- BashTool: 执行 Python 脚本 (MCP 工具名: Bash)
- ReadTool: 读取文件 (MCP 工具名: Read)
- WriteTool: 写入文件 (MCP 工具名: Write)
- ListTool: 列出目录 (MCP 工具名: List)
"""

import json
import shlex
import subprocess
import threading
import queue
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from .base import BaseTool
from ..config import Config


# 输出截断常量（与 Docker 端保持一致）
MAX_OUTPUT_CHARS = 30000
HEAD_RATIO = 0.8


# ============================================================================
# MCP Client
# ============================================================================

class MCPClient:
    """
    MCP 客户端 - 管理 Docker 容器生命周期和 stdio 通信
    """
    
    def __init__(
        self,
        session_id: str,
        workspace_path: Optional[Path] = None,
        skills_path: Optional[Path] = None,
    ):
        self.session_id = session_id
        self.workspace_path = Path(workspace_path) if workspace_path else Config.SESSIONS_ROOT / session_id
        self.skills_path = Path(skills_path) if skills_path else Config.SKILLS_DIR
        
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        
        self._process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._response_queue: queue.Queue = queue.Queue()
        self._reader_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._started = False
        self._initialized = False

    @property
    def _container_name(self) -> str:
        return f"mcp-{self.session_id}"

    def _remove_container(self):
        """显式删除容器，避免 docker 客户端退出后容器残留。"""
        try:
            subprocess.run(
                ["docker", "rm", "-f", self._container_name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
        except Exception as e:
            print(f"[MCP] 清理容器 {self._container_name} 失败: {e}")
    
    def _start_container(self):
        """启动 Docker 容器"""
        if self._process is not None and self._process.poll() is None:
            return

        # 先尝试删除可能存在的同名容器
        self._remove_container()
        
        # 转换路径格式（Windows 兼容）
        workspace_mount = str(self.workspace_path.resolve()).replace("\\", "/")
        skills_mount = str(self.skills_path.resolve()).replace("\\", "/")
        
        cmd = [
            "docker", "run",
            "--rm", "-i",
            "--name", self._container_name,
            "-v", f"{workspace_mount}:/workspace",
            "-v", f"{skills_mount}:/workspace/skills:ro",
            "--cpus", str(Config.DOCKER_CPUS),
            "--memory", Config.DOCKER_MEMORY,
            "--network", "none",
            "-w", "/workspace",
            Config.SANDBOX_IMAGE,
        ]
        
        print(f"[MCP] 启动容器 {self._container_name}...")
        print(f"[MCP] 工作目录: {workspace_mount}")
        print(f"[MCP] Skills 目录: {skills_mount}")
        
        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',  # 替换无法解码的字符
            bufsize=1,
        )
        
        # 启动响应读取线程
        self._reader_thread = threading.Thread(target=self._read_responses, daemon=True)
        self._reader_thread.start()
        
        # 启动错误读取线程（调试用）
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_thread.start()
        
        self._started = True
        print(f"[MCP] [OK] 容器已启动")
    
    def _do_initialize(self):
        """执行 MCP 初始化握手"""
        if self._initialized:
            return
        
        self._request_id += 1
        init_request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "claude-skills-agent",
                    "version": "1.0.0"
                }
            }
        }
        
        try:
            print(f"[MCP] 发送初始化请求...")
            self._process.stdin.write(json.dumps(init_request) + "\n")
            self._process.stdin.flush()
            
            # 等待初始化响应
            print(f"[MCP] 等待初始化响应...")
            response_str = self._response_queue.get(timeout=30)
            print(f"[MCP] 收到响应: {response_str[:200]}...")
            response = json.loads(response_str)
            print(f"[MCP] 初始化响应: {response}")
            
            # 发送 initialized 通知
            initialized_notification = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            self._process.stdin.write(json.dumps(initialized_notification) + "\n")
            self._process.stdin.flush()
            
            self._initialized = True
            print(f"[MCP] [OK] 初始化完成")
            
        except queue.Empty:
            print(f"[MCP] 初始化超时，跳过初始化（可能 MCP Server 不需要初始化）")
            self._initialized = True  # 继续尝试
        except Exception as e:
            print(f"[MCP] 初始化失败: {e}")
            self._initialized = True  # 继续尝试
    
    def _read_responses(self):
        """后台读取 stdout 响应"""
        try:
            while self._process and self._process.poll() is None:
                line = self._process.stdout.readline()
                if line:
                    line = line.strip()
                    if line:
                        self._response_queue.put(line)
                else:
                    if self._process.poll() is not None:
                        break
        except Exception as e:
            print(f"[MCP] stdout 读取异常: {e}")
    
    def _read_stderr(self):
        """后台读取 stderr（调试信息）"""
        try:
            while self._process and self._process.poll() is None:
                line = self._process.stderr.readline()
                if line:
                    print(f"[MCP stderr] {line.strip()}")
        except Exception as e:
            print(f"[MCP] stderr 读取异常: {e}")
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any], timeout: int = 300) -> Dict[str, Any]:
        """调用 MCP 工具"""
        with self._lock:
            self._start_container()
            
            # 确保已初始化
            if not self._initialized:
                import time
                # 等待 reader thread 启动并让 MCP Server 完成预加载
                time.sleep(2.0)
                self._do_initialize()
            
            self._request_id += 1
            request = {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            
            request_json = json.dumps(request, ensure_ascii=False)
            print(f"[MCP] -> 发送请求: {tool_name}")
            
            try:
                self._process.stdin.write(request_json + "\n")
                self._process.stdin.flush()
            except Exception as e:
                raise RuntimeError(f"发送请求失败: {e}")
            
            # 等待响应
            try:
                response_str = self._response_queue.get(timeout=timeout)
                print(f"[MCP] <- 收到响应 ({len(response_str)} 字符)")
                
                response = json.loads(response_str)
                
                if "error" in response:
                    raise RuntimeError(f"MCP Error: {response['error']}")
                
                result = response.get("result", {})
                
                # 解析嵌套的 JSON 字符串
                if isinstance(result, str):
                    return json.loads(result)
                if isinstance(result, dict) and "content" in result:
                    content = result["content"]
                    if isinstance(content, list) and content:
                        text = content[0].get("text", "{}")
                        return json.loads(text)
                    if isinstance(content, str):
                        return json.loads(content)
                return result
                
            except queue.Empty:
                # 超时后重置容器状态
                print(f"[MCP] [WARN] 响应超时，重置容器...")
                self._reset_container()
                raise TimeoutError(f"MCP 响应超时 ({timeout}s)")
            except json.JSONDecodeError as e:
                raise RuntimeError(f"JSON 解析失败: {e}")
    
    def _reset_container(self):
        """重置容器状态（超时或错误后调用）"""
        try:
            if self._process:
                self._process.terminate()
                self._process.wait(timeout=3)
        except:
            if self._process:
                self._process.kill()
        finally:
            self._process = None
            self._started = False
            self._initialized = False
            # 清空响应队列
            while not self._response_queue.empty():
                try:
                    self._response_queue.get_nowait()
                except:
                    pass
            self._remove_container()
        print(f"[MCP] [OK] 容器已重置，下次调用将重新启动")
    
    def cleanup(self):
        """停止容器"""
        print(f"[MCP] 停止容器 {self._container_name}...")
        try:
            if self._process and self._process.stdin:
                self._process.stdin.close()
            if self._process:
                self._process.terminate()
                self._process.wait(timeout=5)
        except Exception:
            if self._process:
                self._process.kill()
        finally:
            self._process = None
            self._started = False
            self._initialized = False
            self._remove_container()
        print(f"[MCP] [OK] 容器 {self._container_name} 已停止")
    
    def __del__(self):
        self.cleanup()


# ============================================================================
# MCP 原子工具基类（Read/Write/List 共用）
# ============================================================================

class MCPToolBase(BaseTool):
    """
    MCP 原子工具基类（Read/Write/List 共用）。

    提供统一的 __init__(mcp_client) 和 _format_result(result) 方法。
    BashTool 返回格式不同，不继承此类。
    """

    def __init__(self, mcp_client: MCPClient):
        self.client = mcp_client

    def _format_result(self, result: Dict[str, Any]) -> str:
        """
        格式化 Read/Write/List 的返回结果。

        这些工具统一返回 {"success": bool, ...} 格式。
        成功时：返回完整 JSON（保留 total_lines/truncated 等元数据，LLM 需据此决策）。
        失败时：返回 error 信息。

        注意：BashTool 返回格式不同，不走此方法。
        """
        if not result.get("success", False):
            return f"Error: {result.get('error', 'Unknown error')}"
        # 成功时，将完整 JSON 返回给 LLM（保留 total_lines/truncated 等元数据）
        return json.dumps(result, ensure_ascii=False)


# ============================================================================
# ReadTool / WriteTool / ListTool
# ============================================================================

class ReadTool(MCPToolBase):
    """读取文件工具"""

    @property
    def name(self) -> str:
        return "Read"

    @property
    def description(self) -> str:
        return """读取文件内容（带分页和自动截断保护）。

默认从文件开头读取最多 2000 行。超过 2000 字符的行自动截断。
返回包含 total_lines 和 truncated 字段，可据此决定翻页或改用脚本处理。

示例：
- Read("uploads/data.csv")
- Read("uploads/big.csv", offset=2000, limit=2000)  # 分页
- Read("skills/fin-advisor-math/SKILL.md")
"""

    @property
    def parameters(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径（相对于 /workspace）"
                },
                "offset": {
                    "type": "integer",
                    "description": "起始行号（0-based），用于分页读取大文件"
                },
                "limit": {
                    "type": "integer",
                    "description": "最大读取行数，默认 2000"
                }
            },
            "required": ["path"]
        }

    def execute(self, path: str, offset: int = 0, limit: int = 2000) -> str:
        args = {"path": path, "offset": offset, "limit": limit}
        try:
            result = self.client.call_tool("Read", args)
        except Exception as e:
            return f"Error: {e}"
        return self._format_result(result)


class WriteTool(MCPToolBase):
    """写入文件工具"""

    @property
    def name(self) -> str:
        return "Write"

    @property
    def description(self) -> str:
        return """写入文件内容（审计留痕）。自动创建父目录。

限制：禁止写入 skills/ 目录（只读），内容不超过 1MB。

示例：
- Write("temp/analysis_001.py", code)  # 临时脚本，配合 Bash 执行
- Write("output/result.json", json_str)
"""

    @property
    def parameters(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径（相对于 /workspace）"
                },
                "content": {
                    "type": "string",
                    "description": "文件内容"
                },
                "append": {
                    "type": "boolean",
                    "description": "是否追加模式，默认覆盖"
                }
            },
            "required": ["path", "content"]
        }

    def execute(self, path: str, content: str, append: bool = False) -> str:
        args = {"path": path, "content": content, "append": append}
        try:
            result = self.client.call_tool("Write", args)
        except Exception as e:
            return f"Error: {e}"
        return self._format_result(result)


class ListTool(MCPToolBase):
    """列出目录工具"""

    @property
    def name(self) -> str:
        return "List"

    @property
    def description(self) -> str:
        return """列出目录内容。返回文件名、类型和大小。

结果超过 500 条时自动截断，返回 total_count 和 truncated 字段。

示例：
- List("uploads/")
- List(".", pattern="*.csv")
- List("skills/", recursive=True)
"""

    @property
    def parameters(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "目录路径（相对于 /workspace），默认当前目录"
                },
                "pattern": {
                    "type": "string",
                    "description": "文件名模式（glob 语法，如 *.csv），默认 *"
                },
                "recursive": {
                    "type": "boolean",
                    "description": "是否递归子目录，默认 false"
                }
            },
            "required": []
        }

    def execute(self, path: str = ".", pattern: str = "*", recursive: bool = False) -> str:
        args = {"path": path, "pattern": pattern, "recursive": recursive}
        try:
            result = self.client.call_tool("List", args)
        except Exception as e:
            return f"Error: {e}"
        return self._format_result(result)


# ============================================================================
# BashTool（精简白名单，仅允许 python/python3）
# ============================================================================

class BashTool(BaseTool):
    """
    Bash 命令执行工具（仅允许 python/python3）
    调用 MCP Server 的 Bash 工具
    """

    ALLOWED_COMMANDS = {'python', 'python3'}
    DANGEROUS_PATTERNS = ['>', '>>', '|', ';', '&&', '||', '`', '$(', 'rm ', 'mv ']

    def __init__(self, mcp_client: MCPClient):
        self.client = mcp_client

    @property
    def name(self) -> str:
        return "Bash"

    @property
    def description(self) -> str:
        return """执行 Python 脚本。仅允许 python/python3 命令。

重要：不要将此工具用于文件操作，请使用专用工具：
- 读取文件 → Read
- 写入文件 → Write
- 列出目录 → List

用法：
1. 执行 Skill CLI 脚本（推荐）：
   Bash("python skills/fin-advisor-math/scripts/finance_formulas.py --type aip --pmt 3000")
2. 执行临时脚本（配合 Write，审计留痕）：
   Bash("python temp/my_script.py")

禁止：python -c（内联代码）和 python -m（模块执行）。
"""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的命令（仅限 python/python3 + .py 文件）"
                }
            },
            "required": ["command"]
        }

    def execute(self, command: str) -> str:
        command = command.strip()
        print(f"\n[Bash] 执行: {command}")

        if not command:
            return "Error: Empty command"

        # 危险字符检查（注入防护，在 shlex 解析前拦截）
        if any(p in command for p in self.DANGEROUS_PATTERNS):
            return "Error: Forbidden characters in command"

        # 使用 shlex.split() 正确处理引号路径
        try:
            parts = shlex.split(command)
        except ValueError as e:
            return f"Error: Invalid command syntax: {e}"

        base_cmd = parts[0]
        if base_cmd not in self.ALLOWED_COMMANDS:
            return f"Error: Only python/python3 allowed, got '{base_cmd}'"

        # 禁止 -c 和 -m
        if len(parts) >= 2 and parts[1] in ('-c', '-m'):
            return "Error: python -c and -m are forbidden. Use Write + Bash for audit trail."

        # 必须执行 .py 文件
        if len(parts) >= 2 and not parts[1].endswith('.py'):
            return "Error: Must execute a .py script file"

        # 调用 MCP
        try:
            result = self.client.call_tool("Bash", {"command": command})
        except Exception as e:
            return f"Error: {e}"

        # 格式化输出（含二次截断保护）
        return self._format_exec_result(result)

    def _format_exec_result(self, result: Dict[str, Any]) -> str:
        """格式化 Bash 返回结果（含输出截断）"""
        output = result.get("stdout", "")
        stderr = result.get("stderr", "")
        exit_code = result.get("exit_code", 0)

        # 二次截断保护（Docker 端已做一次，此处双保险）
        if len(output) > MAX_OUTPUT_CHARS:
            head = int(MAX_OUTPUT_CHARS * HEAD_RATIO)
            tail = MAX_OUTPUT_CHARS - head
            output = (
                output[:head]
                + f"\n\n...[输出被截断，共 {len(output)} 字符]...\n\n"
                + output[-tail:]
            )

        if stderr:
            output += f"\n[stderr]: {stderr}"
        if exit_code != 0:
            output += f"\n[exit_code]: {exit_code}"

        return output or "[No output]"

    def cleanup(self):
        pass  # MCPClient 由外部管理


# ============================================================================
# 工厂函数
# ============================================================================

def create_mcp_tools(
    session_id: str = None,
    uploads_dir: str = None,
) -> Tuple[List[BaseTool], MCPClient]:
    """
    创建 MCP 工具集（Bash, Read, Write, List）及其共享的 MCPClient。
    PythonTool 已移除 — 改用 Write + Bash，便于审计留痕。

    Args:
        session_id: 会话 ID（可选，如果提供 uploads_dir 则忽略）
        uploads_dir: 工作目录路径（用户上传文件所在目录）

    Returns:
        (tools, mcp_client) 元组。调用方应保存 mcp_client 引用用于生命周期管理。
    """
    # 确定工作目录
    if uploads_dir:
        workspace_path = Path(uploads_dir).parent  # uploads 的父目录是 session base
    elif session_id:
        workspace_path = Config.SESSIONS_ROOT / session_id
    else:
        from uuid import uuid4
        session_id = uuid4().hex
        workspace_path = Config.SESSIONS_ROOT / session_id

    workspace_path.mkdir(parents=True, exist_ok=True)

    # 确定 session_id
    if not session_id:
        session_id = workspace_path.name

    # 创建 MCP Client
    mcp_client = MCPClient(
        session_id=session_id,
        workspace_path=workspace_path,
        skills_path=Config.SKILLS_DIR
    )

    # 创建工具
    tools = [
        BashTool(mcp_client),
        ReadTool(mcp_client),
        WriteTool(mcp_client),
        ListTool(mcp_client),
    ]

    return tools, mcp_client
