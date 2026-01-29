"""
MCP 工具模块 - 通过 stdio 与 Docker 容器内的 MCP Server 通信

包含：
- MCPClient: MCP 协议通信
- BashTool: bash 命令执行 (对应 server.py 的 exec_command)
- PythonTool: Python 代码执行 (对应 server.py 的 run_python)
"""

import json
import subprocess
import threading
import queue
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List

from .base import BaseTool
from ..config import Config


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
    
    def _start_container(self):
        """启动 Docker 容器"""
        if self._process is not None and self._process.poll() is None:
            return
        
        container_name = f"mcp-{self.session_id}"
        
        # 先尝试删除可能存在的同名容器
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True
        )
        
        # 转换路径格式（Windows 兼容）
        workspace_mount = str(self.workspace_path.resolve()).replace("\\", "/")
        skills_mount = str(self.skills_path.resolve()).replace("\\", "/")
        
        cmd = [
            "docker", "run",
            "--rm", "-i",
            "--name", container_name,
            "-v", f"{workspace_mount}:/workspace",
            "-v", f"{skills_mount}:/workspace/skills:ro",
            "--cpus", str(Config.DOCKER_CPUS),
            "--memory", Config.DOCKER_MEMORY,
            "--network", "none",
            "-w", "/workspace",
            Config.SANDBOX_IMAGE,
        ]
        
        print(f"[MCP] 启动容器 {container_name}...")
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
        print(f"[MCP] [OK] 容器已重置，下次调用将重新启动")
    
    def cleanup(self):
        """停止容器"""
        if self._process:
            print("[MCP] 停止容器...")
            try:
                self._process.stdin.close()
                self._process.terminate()
                self._process.wait(timeout=5)
            except:
                self._process.kill()
            finally:
                self._process = None
                self._started = False
            print("[MCP] [OK] 容器已停止")
    
    def __del__(self):
        self.cleanup()


# ============================================================================
# BaseTool 实现
# ============================================================================

class BashTool(BaseTool):
    """
    Bash 命令执行工具
    调用 MCP Server 的 exec_command
    """
    
    ALLOWED_COMMANDS = {'cat', 'ls', 'head', 'tail', 'grep', 'find', 'wc', 'pwd', 'file', 'tree', 'python', 'python3'}
    
    def __init__(self, mcp_client: MCPClient):
        self.client = mcp_client
    
    @property
    def name(self) -> str:
        return "bash"
    
    @property
    def description(self) -> str:
        return """执行命令行指令以探索文件系统与运行脚本。

工作目录：/workspace
技能目录：/workspace/skills（只读）

允许的命令：cat, ls, head, tail, grep, find, wc, pwd, file, tree, python, python3

重要提示：
- 技能已通过 Skill 工具注入，无需手动 cat SKILL.md
- 优先使用技能提供的 CLI 脚本（更快更可靠）
- 仅在脚本不适用时才用 run_python_code

示例：
- bash("ls -la uploads/")
- bash("head -20 uploads/data.csv")
- bash("python skills/fin-advisor-math/scripts/finance_formulas.py --type aip --pmt 3000")
"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Bash command to execute"
                }
            },
            "required": ["command"]
        }
    
    def execute(self, command: str) -> str:
        command = command.strip()
        print(f"\n[Bash] 执行: {command}")
        
        if not command:
            return "Error: Empty command"
        
        # 安全检查
        parts = command.split()
        base_cmd = parts[0]
        if base_cmd not in self.ALLOWED_COMMANDS:
            return f"Error: '{base_cmd}' not allowed. Use: {', '.join(sorted(self.ALLOWED_COMMANDS))}"
        
        # Python 命令特殊检查：禁止 -c 和 -m，必须执行 .py 文件
        if base_cmd in ('python', 'python3'):
            if len(parts) < 2:
                return "Error: python command requires a .py script path"
            if parts[1] in ('-c', '-m'):
                return "Error: python -c and -m are forbidden. Execute .py scripts only."
            if not parts[1].endswith('.py'):
                return "Error: python command must run a .py script file"
        
        dangerous = ['>', '>>', '|', ';', '&&', '||', '`', '$(', 'rm ', 'mv ']
        if any(p in command for p in dangerous):
            return "Error: Forbidden characters in command"
        
        # 调用 MCP
        try:
            result = self.client.call_tool("exec_command", {"command": command})
        except Exception as e:
            return f"Error: {e}"
        
        output = result.get("stdout", "")
        if result.get("stderr"):
            output += f"\n[stderr]: {result['stderr']}"
        if result.get("exit_code", 0) != 0:
            output += f"\n[exit_code]: {result['exit_code']}"
        
        return output or "[No output]"
    
    def cleanup(self):
        pass  # MCPClient 由外部管理


class PythonTool(BaseTool):
    """
    Python 代码执行工具（有状态 REPL）
    调用 MCP Server 的 run_python
    """
    
    OUTPUT_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.pdf', '.csv', '.html', '.docx', '.xlsx', '.txt', '.json'}
    
    def __init__(self, mcp_client: MCPClient, output_dir: Optional[Path] = None):
        self.client = mcp_client
        self.output_dir = Path(output_dir) if output_dir else Path("output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def name(self) -> str:
        return "run_python_code"
    
    @property
    def description(self) -> str:
        return """在有状态沙盒中执行 Python 代码（变量跨调用保留）。

预装库：pandas, numpy, matplotlib, seaborn, openpyxl, python-docx

重要提示：
- 适合复杂数据处理与自定义计算
- 优先使用已有脚本/技能指令中的推荐方式
- 需要产出文件时，将文件保存到 /workspace/output/ 目录

使用建议：
- 尽量写完整逻辑，减少拆分调用
- 变量跨调用保留，无需重复导入和加载数据
"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute"
                }
            },
            "required": ["code"]
        }
    
    def execute(self, code: str) -> str:
        print(f"\n[Python] 执行代码 ({len(code)} 字符)")
        print(f"[Python] 代码预览: {code[:200]}{'...' if len(code) > 200 else ''}")
        
        # 记录执行前的文件
        workspace = self.client.workspace_path
        before = self._snapshot_files(workspace)
        
        # 调用 MCP
        try:
            result = self.client.call_tool("run_python", {"code": code})
        except Exception as e:
            return f"执行错误: {e}"
        
        # 构建输出
        lines = []
        
        if result.get("stdout"):
            lines.append("=== 输出 ===")
            lines.append(result["stdout"])
        
        if result.get("result") and result["result"] != "None":
            lines.append("\n=== 返回值 ===")
            lines.append(result["result"])
        
        if result.get("stderr"):
            lines.append("\n=== 信息 ===")
            lines.append(result["stderr"])
        
        if result.get("error"):
            lines.append("\n=== 错误 ===")
            err = result["error"]
            lines.append(f"{err.get('type', 'Error')}: {err.get('message', '')}")
            if err.get("traceback"):
                lines.append(err["traceback"])
        
        # 收集新生成的文件
        after = self._snapshot_files(workspace)
        new_files = after - before
        
        collected = self._collect_output_files(workspace, new_files)
        if collected:
            lines.append("\n=== 生成的文件 ===")
            lines.extend(collected)
        
        final_output = "\n".join(lines) if lines else "代码执行完成（无输出）"
        print(f"[Python] [OK] 执行完成，输出 {len(final_output)} 字符")
        
        return final_output
    
    def _snapshot_files(self, directory: Path) -> set:
        """快照当前目录的文件"""
        if not directory.exists():
            return set()
        return {f.name for f in directory.iterdir() if f.is_file()}
    
    def _collect_output_files(self, workspace: Path, new_files: set) -> List[str]:
        """收集新生成的文件到 output 目录"""
        collected = []
        for fname in new_files:
            fpath = workspace / fname
            if not fpath.exists():
                continue
            
            suffix = fpath.suffix.lower()
            if suffix not in self.OUTPUT_EXTENSIONS:
                continue
            
            # 复制到 output 目录
            target = self.output_dir / fname
            shutil.copy2(fpath, target)
            collected.append(f"[OK] {fname} -> {target}")
            print(f"[Python] [OK] 收集文件: {fname}")
        
        return collected
    
    def cleanup(self):
        pass  # MCPClient 由外部管理


# ============================================================================
# 工厂函数
# ============================================================================

def create_mcp_tools(
    session_id: str = None,
    uploads_dir: str = None,
    output_dir: str = None
) -> List[BaseTool]:
    """
    创建 MCP 工具集（bash, run_python_code）
    
    Args:
        session_id: 会话 ID（可选，如果提供 uploads_dir 则忽略）
        uploads_dir: 工作目录路径（用户上传文件所在目录）
        output_dir: 输出目录路径
        
    Returns:
        包含 BashTool 和 PythonTool 的列表
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
    
    # 确定输出目录
    if output_dir:
        output_path = Path(output_dir)
    else:
        output_path = workspace_path / "output"
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 创建工具
    tools = [
        BashTool(mcp_client),
        PythonTool(mcp_client, output_dir=output_path)
    ]
    
    return tools
