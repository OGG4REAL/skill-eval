 # Docker 本地沙箱迁移技术文档
 
 ## 📖 概述
 
 本文档描述如何将现有的 **E2B 云端沙箱架构** 迁移到 **Docker 本地沙箱架构**，同时保留 Claude Skills Agent 的核心特性：
 
 - ✅ **有状态执行 (Stateful REPL)**：变量跨多次调用存活
 - ✅ **渐进式上下文加载**：三层加载机制完整保留
 - ✅ **Bash Runtime**：Agent 自由探索文件系统
 - ✅ **Docker Volume 挂载**：文件系统直接映射，零拷贝
 - ✅ **MCP 协议通信**：标准化的 stdio 通信
 
 ---
 
 ## 1. 架构对比
 
 ### 1.1 原架构 (E2B)
 
 ```
 ┌─────────────────────────────────────────────────────────────┐
 │  Agent (DeepSeek LLM)                                       │
 │  - bash() 探索本地文件                                       │
 │  - run_python_code() 执行代码                                │
 └─────────────────────────────────────────────────────────────┘
             │ bash("cat ...")              │ run_python_code(...)
             ▼                              ▼
 ┌─────────────────────┐       ┌─────────────────────────────────┐
 │  本地文件系统        │       │  E2B 云端沙盒                   │
 │  - skills/          │       │  - 需要 upload/download         │
 │  - sessions/        │       │  - 依赖 API Key                 │
 └─────────────────────┘       │  - 有网络延迟                   │
                               └─────────────────────────────────┘
 ```
 
 ### 1.2 新架构 (Docker MCP)
 
 ```
 ┌─────────────────────────────────────────────────────────────┐
 │  Agent (DeepSeek LLM)                                       │
 │  - MCP Client 连接 Docker 容器                               │
 │  - 所有操作统一走 MCP 协议                                   │
 └─────────────────────────────────────────────────────────────┘
             │ stdio (MCP Protocol)
             ▼
 ┌─────────────────────────────────────────────────────────────┐
 │  Docker Container (MCP Server)                              │
 │  ┌─────────────────────────────────────────────────────┐   │
 │  │  MCP Server (server.py)                             │   │
 │  │  - run_python(code) → 有状态 REPL                   │   │
 │  │  - exec_command(cmd) → Shell 命令                   │   │
 │  └─────────────────────────────────────────────────────┘   │
 │                                                             │
 │  /workspace (Volume)  ←──映射──→  本地项目目录             │
 │  - skills/                                                  │
 │  - sessions/                                                │
 │  - data.csv                                                 │
 └─────────────────────────────────────────────────────────────┘
 ```
 
 ### 1.3 关键改进
 
 | 维度 | E2B | Docker MCP | 优势 |
 |------|-----|------------|------|
 | **网络** | 需要互联网 | 纯本地 | 离线可用，无延迟 |
 | **费用** | 按用量计费 | 免费 | 无云服务成本 |
 | **文件** | upload/download | Volume 挂载 | 零拷贝，即时同步 |
 | **安全** | 数据在云端 | 数据在本地 | 完全掌控 |
 | **启动** | ~2-5s 冷启动 | ~0.5s | 更快的响应 |
 
 ---
 
 ## 2. Docker 镜像设计
 
 ### 2.1 Dockerfile
 
 ```dockerfile
 # 使用官方 Python 镜像，选择 slim 版本减小体积
 FROM python:3.11-slim
 
 # 设置工作目录
 WORKDIR /app
 
 # 安装系统依赖（用于 pandas, numpy 等科学计算库）
 RUN apt-get update && apt-get install -y --no-install-recommends \
     build-essential \
     && rm -rf /var/lib/apt/lists/*
 
 # 安装 Python 依赖
 COPY requirements.txt /app/
 RUN pip install --no-cache-dir -r requirements.txt
 
 # 复制 MCP Server 代码
 COPY server.py /app/
 
 # 设置默认工作目录为挂载点
 WORKDIR /workspace
 
 # 启动 MCP Server
 CMD ["python", "/app/server.py"]
 ```
 
 ### 2.2 requirements.txt
 
 ```txt
 # MCP SDK
 mcp>=1.0.0
 
 # 数据科学常用库
 pandas>=2.0.0
 numpy>=1.24.0
 openpyxl>=3.1.0
 
 # JSON 处理
 orjson>=3.9.0
 
 # 可选：如果需要更复杂的依赖管理
 # ipython>=8.0.0  # 用于更高级的 REPL 功能
 ```
 
 ### 2.3 构建命令
 
 ```bash
 # 构建镜像
 docker build -t claude-skills-sandbox:latest .
 
 # 验证镜像
 docker images | grep claude-skills-sandbox
 ```
 
 ---
 
 ## 3. MCP Server 实现 (核心代码)
 
 ### 3.1 server.py - 完整实现
 
 ```python
 """
 Claude Skills Agent - Docker MCP Server
 
 实现两个核心工具：
 1. run_python: 有状态的 Python REPL（变量跨调用保留）
 2. exec_command: Bash 命令执行
 
 通信方式: stdio (标准输入/输出)
 """
 
 import sys
 import subprocess
 import traceback
 from io import StringIO
 from contextlib import redirect_stdout, redirect_stderr
 from typing import Any, Dict
 
 from mcp.server.fastmcp import FastMCP
 
 # ============================================================================
 # 全局状态：Python 解释器上下文
 # ============================================================================
 
 # 这个字典是"有状态"的核心：所有执行的代码共享这个命名空间
 # 类似于 Jupyter Kernel 的全局变量空间
 _GLOBAL_CONTEXT: Dict[str, Any] = {
     "__builtins__": __builtins__,  # 保留内置函数
 }
 
 # 执行计数器（模拟 Jupyter 的 In[n]）
 _EXECUTION_COUNT = 0
 
 # ============================================================================
 # MCP Server 初始化
 # ============================================================================
 
 mcp = FastMCP(
     name="ClaudeSkillsSandbox",
     version="1.0.0",
 )
 
 # ============================================================================
 # 工具定义
 # ============================================================================
 
 @mcp.tool()
 def run_python(code: str) -> str:
     """
     在有状态的 Python 环境中执行代码。
     
     特性：
     - 变量会在多次调用之间保留（如 Jupyter Kernel）
     - 支持 import 语句，导入的模块会保留
     - 支持 print() 输出
     - 自动捕获最后一个表达式的值
     
     参数：
         code: 要执行的 Python 代码
         
     返回：
         JSON 格式的执行结果，包含 success, stdout, stderr, result, error
         
     示例：
         # 第一次调用
         run_python("import pandas as pd; df = pd.read_csv('data.csv')")
         
         # 第二次调用（df 变量仍然存在）
         run_python("print(df.head())")
     """
     global _EXECUTION_COUNT, _GLOBAL_CONTEXT
     _EXECUTION_COUNT += 1
     
     # 捕获输出
     stdout_capture = StringIO()
     stderr_capture = StringIO()
     result_value = None
     error_info = None
     
     try:
         with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
             # 尝试作为表达式求值（用于获取最后一个值）
             try:
                 # 先尝试 eval（适用于单个表达式）
                 result_value = eval(code, _GLOBAL_CONTEXT)
             except SyntaxError:
                 # 如果是语句（如 import, 赋值），使用 exec
                 exec(code, _GLOBAL_CONTEXT)
                 result_value = None
                 
     except Exception as e:
         error_info = {
             "type": type(e).__name__,
             "message": str(e),
             "traceback": traceback.format_exc()
         }
     
     # 构造返回结果（简洁格式）
     response = {
         "success": error_info is None,
         "stdout": stdout_capture.getvalue(),   # 代码 print() 的原始内容
         "stderr": stderr_capture.getvalue(),
         "result": repr(result_value) if result_value is not None else None,
         "error": error_info
     }
     
     # 返回 JSON 字符串
     import json
     return json.dumps(response, ensure_ascii=False, indent=2)
 
 
 @mcp.tool()
 def exec_command(command: str, timeout: int = 30) -> str:
     """
     在 Shell 中执行命令（Bash Runtime）。
     
     用于：
     - 探索文件系统：ls, cat, head, grep 等
     - 安装依赖：pip install xxx
     - 运行脚本：python script.py
     
     参数：
         command: 要执行的 Shell 命令
         timeout: 超时时间（秒），默认 30 秒
         
     返回：
         JSON 格式的执行结果，包含 stdout, stderr, exit_code
         
     示例：
         exec_command("ls -la /workspace/skills/")
         exec_command("cat /workspace/skills/csv-data-summarizer/SKILL.md")
         exec_command("head -20 /workspace/data.csv")
     """
     try:
         result = subprocess.run(
             command,
             shell=True,
             capture_output=True,
             text=True,
             timeout=timeout,
             cwd="/workspace"  # 默认在工作目录执行
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
     
     import json
     return json.dumps(response, ensure_ascii=False, indent=2)
 
 
 @mcp.tool()
 def reset_context() -> str:
     """
     重置 Python 执行上下文，清除所有变量。
     
     用于：
     - 开始新的分析任务
     - 清理内存
     - 解决变量污染问题
     
     返回：
         确认信息
     """
     global _GLOBAL_CONTEXT, _EXECUTION_COUNT
     _GLOBAL_CONTEXT = {
         "__builtins__": __builtins__,
     }
     _EXECUTION_COUNT = 0
     return '{"status": "ok", "message": "Context reset successfully"}'
 
 
 @mcp.tool()
 def get_context_vars() -> str:
     """
     获取当前上下文中的所有变量名及其类型。
     
     用于：
     - 调试：查看当前环境中有哪些变量
     - 规划：决定下一步操作
     
     返回：
         JSON 格式的变量列表
     """
     import json
     
     vars_info = {}
     for name, value in _GLOBAL_CONTEXT.items():
         # 跳过内置对象和私有变量
         if name.startswith("_") or name == "__builtins__":
             continue
         vars_info[name] = {
             "type": type(value).__name__,
             "repr": repr(value)[:100] + "..." if len(repr(value)) > 100 else repr(value)
         }
     
     return json.dumps({
         "execution_count": _EXECUTION_COUNT,
         "variables": vars_info
     }, ensure_ascii=False, indent=2)
 
 
 # ============================================================================
 # 启动服务
 # ============================================================================
 
 if __name__ == "__main__":
     # 通过 stdio 运行 MCP Server
     mcp.run()
 ```
 
 ### 3.2 代码说明
 
 #### 核心设计：有状态 REPL
 
 ```python
 # 这是实现"有状态"的关键
 _GLOBAL_CONTEXT: Dict[str, Any] = {
     "__builtins__": __builtins__,
 }
 
 # 所有代码都在这个字典中执行
 exec(code, _GLOBAL_CONTEXT)
 ```
 
 **工作原理**：
 1. `_GLOBAL_CONTEXT` 是一个全局字典，作为所有代码执行的命名空间
 2. 当 Agent 执行 `x = 10` 时，`x` 被存入 `_GLOBAL_CONTEXT["x"] = 10`
 3. 下次执行 `print(x)` 时，从 `_GLOBAL_CONTEXT` 中读取 `x` 的值
 4. 这模拟了 Jupyter Kernel 的行为
 
 #### 两层输出设计
 
 本系统的输出分为两层，各司其职：
 
 **Layer 1: MCP 通信层（传输管道）**
 
 `run_python` 工具返回的 JSON 格式，职责是忠实传递执行结果：
 
 ```json
 {
   "success": true,
   "stdout": "代码 print() 的原始内容",
   "stderr": "",
   "result": "表达式的值（如果有）",
   "error": null
 }
 ```
 
 **Layer 2: 业务输出层（由 Skill 定义）**
 
 `stdout` 字段的内容由 Skill 中的代码决定，可以是：
 
 - **纯文本**：`print("加权毛利率: 65.22%")`
 - **JSON 文本**：`print(json.dumps({"charts": [...]}))` → 前端解析为 ECharts 图表
 - **带标记的混合内容**：
   ```python
   print("分析完成！")
   print("ANALYSIS_RESULT_START")
   print(json.dumps(chart_config))
   print("ANALYSIS_RESULT_END")
   ```
 
 **设计理念**：Agent 的输出永远是文本（最擅长的形式），复杂性（图表渲染）留给前端处理。
 
 ---
 
 ## 4. Agent 端修改指南
 
 ### 4.1 新建 Docker 执行器
 
 创建 `agent_system/tools/docker_executor.py`：
 
 ```python
 """
 Docker MCP 执行器
 
 替代原有的 E2B 执行器，通过 MCP 协议与本地 Docker 容器通信。
 """
 
 import os
 import json
 import subprocess
 from typing import Optional, Dict, Any, List
 from dataclasses import dataclass
 
 from agent_system.tools.base import BaseTool
 
 
 @dataclass
 class ExecutionResult:
     """代码执行结果"""
     success: bool
     stdout: str           # 代码 print() 的原始内容（可能是纯文本或 JSON）
     stderr: str
     result: Optional[str] = None
     error: Optional[Dict[str, str]] = None
 
 
 class DockerMCPExecutor(BaseTool):
     """
     Docker MCP 执行器
     
     通过 stdio 与 Docker 容器内的 MCP Server 通信。
     """
     
     name = "run_python_code"
     description = "在 Docker 沙箱中执行 Python 代码（支持有状态执行）"
     
     def __init__(
         self,
         image_name: str = "claude-skills-sandbox:latest",
         workspace_path: Optional[str] = None,
         session_id: Optional[str] = None,
     ):
         """
         初始化 Docker MCP 执行器
         
         Args:
             image_name: Docker 镜像名称
             workspace_path: 要挂载的本地工作目录（默认为当前目录）
             session_id: 会话 ID（用于日志和输出目录）
         """
         self.image_name = image_name
         self.workspace_path = workspace_path or os.getcwd()
         self.session_id = session_id
         
         # Docker 进程（保持容器运行以实现有状态执行）
         self._container_process: Optional[subprocess.Popen] = None
         
     def _ensure_container_running(self):
         """确保容器正在运行"""
         if self._container_process is None or self._container_process.poll() is not None:
             # 启动新容器
             self._container_process = subprocess.Popen(
                 [
                     "docker", "run",
                     "--rm",           # 退出时自动删除容器
                     "-i",             # 保持 stdin 打开（用于 stdio 通信）
                     "-v", f"{self.workspace_path}:/workspace",  # 挂载工作目录
                     "-w", "/workspace",  # 设置工作目录
                     self.image_name
                 ],
                 stdin=subprocess.PIPE,
                 stdout=subprocess.PIPE,
                 stderr=subprocess.PIPE,
                 text=True,
                 bufsize=1  # 行缓冲
             )
     
     def _send_mcp_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
         """
         发送 MCP 请求并获取响应
         
         这是一个简化的 MCP 客户端实现。
         实际项目中建议使用官方的 mcp 库。
         """
         self._ensure_container_running()
         
         # 构造 JSON-RPC 请求
         request = {
             "jsonrpc": "2.0",
             "id": 1,
             "method": method,
             "params": params
         }
         
         # 发送请求
         request_str = json.dumps(request) + "\n"
         self._container_process.stdin.write(request_str)
         self._container_process.stdin.flush()
         
         # 读取响应
         response_str = self._container_process.stdout.readline()
         response = json.loads(response_str)
         
         if "error" in response:
             raise Exception(f"MCP Error: {response['error']}")
         
         return response.get("result", {})
     
     def execute(
         self,
         code: str,
         input_files: Optional[List[str]] = None,  # 保留参数兼容性，但不再需要
     ) -> ExecutionResult:
         """
         执行 Python 代码
         
         Args:
             code: 要执行的 Python 代码
             input_files: [已弃用] 输入文件列表（现在通过 Volume 挂载自动可用）
             
         Returns:
             ExecutionResult: 执行结果
         """
         # 调用 MCP 工具
         result = self._send_mcp_request(
             method="tools/call",
             params={
                 "name": "run_python",
                 "arguments": {"code": code}
             }
         )
         
         # 解析返回的 JSON 字符串
         if isinstance(result, str):
             result = json.loads(result)
         
         return ExecutionResult(
             success=result.get("success", True),
             stdout=result.get("stdout", ""),
             stderr=result.get("stderr", ""),
             result=result.get("result"),
             error=result.get("error")
         )
     
     def exec_bash(self, command: str, timeout: int = 30) -> Dict[str, Any]:
         """
         执行 Bash 命令
         
         Args:
             command: Shell 命令
             timeout: 超时时间（秒）
             
         Returns:
             执行结果字典
         """
         result = self._send_mcp_request(
             method="tools/call",
             params={
                 "name": "exec_command",
                 "arguments": {"command": command, "timeout": timeout}
             }
         )
         
         if isinstance(result, str):
             result = json.loads(result)
         
         return result
     
     def reset(self):
         """重置执行上下文"""
         self._send_mcp_request(
             method="tools/call",
             params={"name": "reset_context", "arguments": {}}
         )
     
     def cleanup(self):
         """清理资源，关闭容器"""
         if self._container_process:
             self._container_process.terminate()
             self._container_process.wait()
             self._container_process = None
     
     def __del__(self):
         self.cleanup()
 ```
 
 ### 4.2 修改原有的 python_executor.py
 
 **修改前（E2B）**：
 ```python
 # agent_system/tools/python_executor.py (原代码)
 
 from e2b_code_interpreter import Sandbox
 
 class PythonExecutorTool(BaseTool):
     def __init__(self, session_id: str):
         self.sandbox = Sandbox()  # E2B 沙盒
         self.session_id = session_id
     
     def execute(self, code: str, input_files: List[str] = None):
         # 上传文件到 E2B
         for file in input_files:
             self.sandbox.upload_file(file)
         
         # 执行代码
         result = self.sandbox.run_code(code)
         
         # 下载生成的文件
         for file in self._detect_output_files():
             self.sandbox.download_file(file, f"sessions/{self.session_id}/output/")
         
         return result
 ```
 
 **修改后（Docker MCP）**：
 ```python
 # agent_system/tools/python_executor.py (新代码)
 
 from agent_system.tools.docker_executor import DockerMCPExecutor
 
 class PythonExecutorTool(BaseTool):
     def __init__(self, session_id: str, workspace_path: str = None):
         # 使用 Docker MCP 执行器替代 E2B
         self.executor = DockerMCPExecutor(
             workspace_path=workspace_path or os.getcwd(),
             session_id=session_id
         )
         self.session_id = session_id
     
     def execute(self, code: str, input_files: List[str] = None):
         # 文件已经通过 Volume 挂载，无需上传
         # input_files 参数保留是为了向后兼容，但不再使用
         
         result = self.executor.execute(code)
         
         # 输出文件已经在本地，无需下载
         # 只需检查是否生成了文件即可
         
         return result
     
     def cleanup(self):
         """会话结束时清理"""
         self.executor.cleanup()
 ```
 
 ### 4.3 修改 Bash Runtime
 
 **修改前**：Bash 在宿主机执行  
 **修改后**：Bash 在容器内执行（与 Python 共享文件系统）
 
 ```python
 # agent_system/tools/bash_runtime.py (修改版)
 
 class BashRuntimeTool(BaseTool):
     """
     Bash 命令执行工具
     
     现在通过 Docker MCP 执行，与 Python 环境共享文件系统。
     """
     
     def __init__(self, docker_executor: DockerMCPExecutor):
         self.executor = docker_executor
     
     def execute(self, command: str) -> str:
         """执行 bash 命令"""
         result = self.executor.exec_bash(command)
         
         # 格式化输出
         if result["status"] == "completed":
             output = result["stdout"]
             if result["stderr"]:
                 output += f"\n[STDERR]: {result['stderr']}"
             return output
         else:
             return f"[ERROR]: {result['stderr']}"
 ```
 
 ### 4.4 修改 Agent 初始化
 
 ```python
 # agent_system/agent/core.py
 
 class Agent:
     def __init__(self, session_id: str, workspace_path: str = None):
         self.session_id = session_id
         self.workspace_path = workspace_path or os.getcwd()
         
         # 初始化 Docker 执行器（所有工具共享）
         self.docker_executor = DockerMCPExecutor(
             workspace_path=self.workspace_path,
             session_id=session_id
         )
         
         # 初始化工具
         self.tools = {
             "bash": BashRuntimeTool(self.docker_executor),
             "run_python_code": PythonExecutorTool(
                 session_id=session_id,
                 workspace_path=workspace_path,
                 executor=self.docker_executor  # 共享执行器
             ),
         }
     
     def cleanup(self):
         """清理资源"""
         self.docker_executor.cleanup()
 ```
 
 ---
 
 ## 5. 使用方式
 
 ### 5.1 构建并运行
 
 ```bash
 # 1. 进入沙箱目录
 cd docker-sandbox/
 
 # 2. 构建镜像
 docker build -t claude-skills-sandbox:latest .
 
 # 3. 测试运行（手动）
 docker run --rm -it \
   -v $(pwd):/workspace \
   claude-skills-sandbox:latest
 
 # 在容器内测试 MCP 通信
 # （输入 JSON-RPC 请求，观察响应）
 ```
 
 ### 5.2 Agent 调用流程
 
 ```python
 # 示例：Agent 分析 CSV 文件
 
 from agent_system.agent import Agent
 
 # 初始化 Agent，指定工作目录
 agent = Agent(
     session_id="session_001",
     workspace_path="/path/to/your/project"
 )
 
 try:
     # Agent 执行任务
     result = agent.run("分析 data.csv 文件，生成财务报告")
     print(result)
 finally:
     # 清理资源
     agent.cleanup()
 ```
 
 ### 5.3 渐进式执行示例
 
 ```python
 # 模拟 Agent 的渐进式执行
 
 # 第1步：探索技能目录
 agent.tools["bash"].execute("ls skills/")
 # → csv-data-summarizer/  docx/
 
 # 第2步：阅读技能文档
 agent.tools["bash"].execute("cat skills/csv-data-summarizer/SKILL.md")
 # → [完整的技能文档]
 
 # 第3步：预览数据
 agent.tools["bash"].execute("head -20 data.csv")
 # → [CSV 前20行]
 
 # 第4步：执行分析代码（有状态）
 agent.tools["run_python_code"].execute("""
 import pandas as pd
 df = pd.read_csv('data.csv')
 print(f"数据形状: {df.shape}")
 """)
 # → 数据形状: (1000, 15)
 
 # 第5步：继续分析（df 变量仍然存在）
 agent.tools["run_python_code"].execute("""
 # df 变量在上一步已经加载，无需重新读取
 summary = df.describe()
 print(summary)
 """)
 # → [数据统计摘要]
 
 # 第6步：生成 JSON 结果
 agent.tools["run_python_code"].execute("""
 import json
 
 result = {
     "summary": {
         "total_rows": len(df),
         "columns": list(df.columns),
         "revenue_total": float(df['revenue'].sum())
     },
     "charts": [
         {"type": "line", "title": "Revenue Trend", "data": [...]}
     ]
 }
 
 # 保存到文件（会立即出现在本地 workspace 目录）
 with open('analysis_result.json', 'w') as f:
     json.dump(result, f, indent=2)
 
 print("ANALYSIS_RESULT_START")
 print(json.dumps(result, indent=2))
 print("ANALYSIS_RESULT_END")
 """)
 ```
 
 ---
 
 ## 6. 迁移检查清单
 
 ### 6.1 代码修改
 
 - [ ] 创建 `docker-sandbox/` 目录
 - [ ] 创建 `docker-sandbox/Dockerfile`
 - [ ] 创建 `docker-sandbox/requirements.txt`
 - [ ] 创建 `docker-sandbox/server.py` (MCP Server)
 - [ ] 创建 `agent_system/tools/docker_executor.py`
 - [ ] 修改 `agent_system/tools/python_executor.py`
 - [ ] 修改 `agent_system/tools/bash_runtime.py`
 - [ ] 修改 `agent_system/agent/core.py`
 
 ### 6.2 删除 E2B 相关代码
 
 - [ ] 删除 `e2b` 相关依赖
 - [ ] 删除 `E2B_API_KEY` 环境变量配置
 - [ ] 删除所有 `sandbox.upload_file()` 调用
 - [ ] 删除所有 `sandbox.download_file()` 调用
 
 ### 6.3 环境配置
 
 - [ ] 安装 Docker Desktop / Docker Engine
 - [ ] 构建 `claude-skills-sandbox` 镜像
 - [ ] 更新 `.env` 配置（如有需要）
 
 ### 6.4 测试验证
 
 - [ ] 测试 `exec_command` 工具（ls, cat, head）
 - [ ] 测试 `run_python` 工具（单次执行）
 - [ ] 测试有状态执行（变量跨调用保留）
 - [ ] 测试文件读写（通过 Volume 挂载）
 - [ ] 测试完整的 Agent 流程
 
 ---
 
 ## 7. 高级配置（可选）
 
 ### 7.1 资源限制
 
 ```bash
 # 限制容器资源使用
 docker run --rm -i \
   --memory=2g \        # 限制内存 2GB
   --cpus=2 \           # 限制 CPU 核数
   -v $(pwd):/workspace \
   claude-skills-sandbox:latest
 ```
 
 ### 7.2 网络隔离
 
 ```bash
 # 完全禁用网络（安全模式）
 docker run --rm -i \
   --network=none \
   -v $(pwd):/workspace \
   claude-skills-sandbox:latest
 ```
 
 ### 7.3 预装更多依赖
 
 修改 `requirements.txt`：
 
 ```txt
 # 数据处理
 pandas>=2.0.0
 numpy>=1.24.0
 openpyxl>=3.1.0
 xlrd>=2.0.0
 
 # 可视化（如果需要生成图片）
 matplotlib>=3.7.0
 seaborn>=0.12.0
 
 # 机器学习
 scikit-learn>=1.2.0
 
 # 文件处理
 python-docx>=0.8.11
 PyPDF2>=3.0.0
 ```
 
 ### 7.4 持久化存储（跨会话）
 
 如果需要在多次 Agent 会话间保持某些数据：
 
 ```bash
 # 创建命名卷
 docker volume create claude-skills-data
 
 # 挂载持久化卷
 docker run --rm -i \
   -v claude-skills-data:/persistent \
   -v $(pwd):/workspace \
   claude-skills-sandbox:latest
 ```
 
 ---
 
 ## 8. 故障排查
 
 ### 问题 1: 容器无法启动
 
 ```bash
 # 检查 Docker 是否运行
 docker info
 
 # 检查镜像是否存在
 docker images | grep claude-skills-sandbox
 
 # 手动运行容器调试
 docker run --rm -it claude-skills-sandbox:latest /bin/bash
 ```
 
 ### 问题 2: 文件权限问题
 
 ```bash
 # Linux/Mac: 确保挂载目录有正确权限
 chmod -R 755 /your/workspace/path
 
 # 或在 Dockerfile 中设置用户
 RUN useradd -m sandbox
 USER sandbox
 ```
 
 ### 问题 3: MCP 通信失败
 
 ```python
 # 调试：打印原始通信内容
 import json
 
 request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", ...}
 print(f"Sending: {json.dumps(request)}")
 
 # 检查 Docker 日志
 # docker logs <container_id>
 ```
 
 ### 问题 4: 变量状态丢失
 
 确保：
 1. 容器进程没有重启（检查 `_container_process.poll()`）
 2. 没有调用 `reset_context()`
 3. 代码没有语法错误导致执行中断
 
 ---
 
 ## 9. 总结
 
 ### 迁移收益
 
 | 指标 | E2B | Docker MCP | 提升 |
 |------|-----|------------|------|
 | 启动时间 | 2-5s | 0.3-0.5s | **10x** |
 | 文件传输 | 需要上传/下载 | 零拷贝 | **∞** |
 | 成本 | $0.1/分钟 | 免费 | **100%** |
 | 离线可用 | ❌ | ✅ | - |
 | 数据安全 | 云端 | 本地 | - |
 
 ### 保留的核心能力
 
 - ✅ **Bash Runtime**：Agent 自由探索文件系统
 - ✅ **三层加载**：元数据 → SKILL.md → 参考代码
 - ✅ **有状态执行**：变量跨调用保留
 - ✅ **文本输出**：Agent 输出纯文本或 JSON 文本，前端按约定解析渲染
 
 ### 下一步
 
 1. 按照本文档完成代码迁移
 2. 构建并测试 Docker 镜像
 3. 运行完整的 Agent 测试用例
 4. 根据需要调整资源限制和依赖
 
 ---
 
 ## 10. 多租户与产品化（规划）
 
 > ⚠️ 本章节为产品上线时的架构规划，Demo 阶段可跳过。
 
 ### 10.1 问题背景
 
 Demo 阶段使用 Volume 挂载本地目录是可行的，但产品化后面临以下问题：
 
 | 问题 | 说明 |
 |------|------|
 | **用户隔离** | 每个用户/会话需要独立容器，不能共享文件系统 |
 | **安全性** | 不能将服务器文件系统暴露给用户 |
 | **Skills 管理** | 不同用户可能需要不同的 Skills 子集 |
 | **用户数据** | 用户上传的文件需要动态注入，而非预先挂载 |
 
 ### 10.2 解决方案：分层架构
 
 ```
 ┌─────────────────────────────────────────────────────────────────┐
 │  文件类型        │  特点              │  解决方案               │
 ├─────────────────────────────────────────────────────────────────┤
 │  Skills 文件     │  静态、公共、只读  │  预打包到镜像            │
 │  用户上传数据    │  动态、私有、读写  │  通过 MCP write_file 写入│
 │  执行输出       │  临时、私有        │  容器内存储，MCP 读取    │
 └─────────────────────────────────────────────────────────────────┘
 ```
 
 ### 10.3 Skills 预打包到镜像
 
 修改 Dockerfile，在构建时将 Skills 复制进去：
 
 ```dockerfile
 FROM python:3.11-slim
 
 # ... 安装依赖 ...
 
 # 在构建时将 Skills 复制到镜像内
 COPY skills/ /app/skills/
 
 # 设置环境变量，让 Agent 知道 Skills 在哪
 ENV SKILLS_PATH=/app/skills
 
 WORKDIR /workspace
 CMD ["python", "/app/server.py"]
 ```
 
 ### 10.4 运行时 Skills 过滤
 
 通过环境变量控制用户可见的 Skills：
 
 ```bash
 # 启动容器时指定允许的 Skills
 docker run -e ALLOWED_SKILLS=csv-data-summarizer,docx-generator \
   claude-skills-sandbox:latest
 ```
 
 在 `server.py` 中实现过滤逻辑：
 
 ```python
 import os
 
 ALLOWED_SKILLS = os.getenv("ALLOWED_SKILLS", "*").split(",")
 
 @mcp.tool()
 def exec_command(command: str, timeout: int = 30) -> str:
     # 拦截对非授权 Skills 的访问
     if "/app/skills/" in command:
         skill_name = command.split("/app/skills/")[1].split("/")[0]
         if ALLOWED_SKILLS != ["*"] and skill_name not in ALLOWED_SKILLS:
             return json.dumps({
                 "success": False,
                 "stdout": "",
                 "stderr": "Access denied: skill not available",
                 "error": {"type": "PermissionError", "message": "Skill not authorized"}
             })
     
     # ... 正常执行 ...
 ```
 
 ### 10.5 用户数据动态写入
 
 添加 `write_file` 工具，允许通过 MCP 将用户文件写入容器：
 
 ```python
 @mcp.tool()
 def write_file(path: str, content: str, encoding: str = "utf-8") -> str:
     """
     将内容写入容器内的文件。
     
     用于：用户上传的数据文件、Agent 生成的中间文件
     
     参数：
         path: 文件路径（相对于 /workspace）
         content: 文件内容
         encoding: 编码方式
     """
     import os
     
     # 安全检查：只允许写入 /workspace 目录
     full_path = os.path.join("/workspace", path.lstrip("/"))
     if not full_path.startswith("/workspace"):
         return json.dumps({
             "success": False,
             "error": {"type": "SecurityError", "message": "Can only write to /workspace"}
         })
     
     # 创建目录并写入文件
     os.makedirs(os.path.dirname(full_path), exist_ok=True)
     with open(full_path, "w", encoding=encoding) as f:
         f.write(content)
     
     return json.dumps({"success": True, "path": full_path})
 ```
 
 ### 10.6 容器编排（生产环境）
 
 ```
 ┌─────────────────────────────────────────────────────────────────┐
 │                        API Gateway                              │
 │  - 用户认证、会话管理、请求路由                                  │
 └─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │                   Container Orchestrator                        │
 │  - 根据用户类型选择镜像                                          │
 │  - 设置 ALLOWED_SKILLS 环境变量                                  │
 │  - 分配资源限制、管理容器生命周期                                │
 └─────────────────────────────────────────────────────────────────┘
             │                    │                    │
             ▼                    ▼                    ▼
 ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
 │ Container: User A │ │ Container: User B │ │ Container: User C │
 │ Skills: financial │ │ Skills: coding    │ │ Skills: full      │
 │ /workspace (隔离) │ │ /workspace (隔离) │ │ /workspace (隔离) │
 └───────────────────┘ └───────────────────┘ └───────────────────┘
 ```
 
 ### 10.7 演进路径
 
 | 阶段 | 方案 | 适用场景 |
 |------|------|----------|
 | **Demo** | Volume 挂载本地目录 | 开发测试 |
 | **Alpha** | Skills 预打包 + write_file | 少量用户 |
 | **Beta** | 分层镜像 + 环境变量过滤 | 多用户类型 |
 | **正式** | K8s + 动态调度 | 大规模多租户 |
 
 ---
 
 **🚀 祝迁移顺利！**
