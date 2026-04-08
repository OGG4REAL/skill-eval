"""
MCP 工具类 Python 侧单元测试

测试目标：agent_system/tools/mcp_tools.py 中的
- MCPToolBase._format_result()
- ReadTool / WriteTool / ListTool（参数、描述、execute 调用链）
- BashTool（白名单、shlex 解析、危险字符检查、输出截断、-c/-m 拒绝）
- create_mcp_tools 工厂函数

注意：这里不启动真实 Docker 容器，所有 MCP 调用通过 Mock 模拟。

运行方式:
    python -m pytest tests/test_mcp_tool_classes.py -v
    或直接运行: python tests/test_mcp_tool_classes.py
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_system.tools.mcp_tools import (
    MCPToolBase,
    ReadTool,
    WriteTool,
    ListTool,
    BashTool,
    MCPClient,
    MAX_OUTPUT_CHARS,
    HEAD_RATIO,
    create_mcp_tools,
)
from agent_system.tools.base import BaseTool


# ============================================================================
# 测试辅助
# ============================================================================

def make_mock_client() -> MagicMock:
    """创建 Mock MCP Client"""
    client = MagicMock(spec=MCPClient)
    return client


# ============================================================================
# 1. MCPToolBase._format_result 测试
# ============================================================================

class TestMCPToolBaseFormatResult:
    """MCPToolBase._format_result 公共方法测试"""

    def _make_tool(self):
        """创建一个具体的 MCPToolBase 子类实例用于测试"""
        client = make_mock_client()
        return ReadTool(client)

    def test_success_returns_json(self):
        """成功时返回完整 JSON"""
        tool = self._make_tool()
        result = {"success": True, "content": "hello", "lines_read": 1, "total_lines": 1}
        output = tool._format_result(result)
        parsed = json.loads(output)
        assert parsed["success"] is True
        assert parsed["content"] == "hello"

    def test_failure_returns_error_string(self):
        """失败时返回 Error: 开头的字符串"""
        tool = self._make_tool()
        result = {"success": False, "error": "文件不存在"}
        output = tool._format_result(result)
        assert output.startswith("Error:")
        assert "文件不存在" in output

    def test_failure_no_error_field(self):
        """失败时缺少 error 字段"""
        tool = self._make_tool()
        result = {"success": False}
        output = tool._format_result(result)
        assert "Unknown error" in output

    def test_success_preserves_chinese(self):
        """成功时正确保留中文"""
        tool = self._make_tool()
        result = {"success": True, "content": "你好世界", "encoding": "utf-8"}
        output = tool._format_result(result)
        assert "你好世界" in output


# ============================================================================
# 2. ReadTool 测试
# ============================================================================

class TestReadTool:
    """ReadTool 工具类测试"""

    def test_name(self):
        tool = ReadTool(make_mock_client())
        assert tool.name == "Read"

    def test_inherits_base_tool(self):
        tool = ReadTool(make_mock_client())
        assert isinstance(tool, BaseTool)
        assert isinstance(tool, MCPToolBase)

    def test_parameters_schema(self):
        tool = ReadTool(make_mock_client())
        params = tool.parameters
        assert params["type"] == "object"
        assert "path" in params["properties"]
        assert "offset" in params["properties"]
        assert "limit" in params["properties"]
        assert params["required"] == ["path"]

    def test_execute_calls_mcp_read(self):
        """execute 正确调用 MCP Read"""
        client = make_mock_client()
        client.call_tool.return_value = {
            "success": True,
            "content": "     1|hello",
            "encoding": "utf-8",
            "lines_read": 1,
            "total_lines": 1,
            "truncated": False
        }
        tool = ReadTool(client)
        result = tool.execute(path="uploads/test.csv")
        client.call_tool.assert_called_once_with("Read", {"path": "uploads/test.csv", "offset": 0, "limit": 2000})
        parsed = json.loads(result)
        assert parsed["success"] is True

    def test_execute_with_offset_limit(self):
        """execute 传递 offset 和 limit"""
        client = make_mock_client()
        client.call_tool.return_value = {"success": True, "content": "", "lines_read": 0, "total_lines": 100, "truncated": True}
        tool = ReadTool(client)
        tool.execute(path="uploads/big.csv", offset=50, limit=10)
        client.call_tool.assert_called_once_with("Read", {"path": "uploads/big.csv", "offset": 50, "limit": 10})

    def test_execute_mcp_error(self):
        """MCP 调用异常时返回 Error"""
        client = make_mock_client()
        client.call_tool.side_effect = RuntimeError("容器未启动")
        tool = ReadTool(client)
        result = tool.execute(path="uploads/fail.csv")
        assert result.startswith("Error:")
        assert "容器未启动" in result

    def test_to_function_definition(self):
        """to_function_definition 输出 OpenAI 格式"""
        tool = ReadTool(make_mock_client())
        fd = tool.to_function_definition()
        assert fd["type"] == "function"
        assert fd["function"]["name"] == "Read"
        assert "path" in fd["function"]["parameters"]["properties"]


# ============================================================================
# 3. WriteTool 测试
# ============================================================================

class TestWriteTool:
    """WriteTool 工具类测试"""

    def test_name(self):
        tool = WriteTool(make_mock_client())
        assert tool.name == "Write"

    def test_parameters_schema(self):
        tool = WriteTool(make_mock_client())
        params = tool.parameters
        assert "path" in params["properties"]
        assert "content" in params["properties"]
        assert "append" in params["properties"]
        assert "path" in params["required"]
        assert "content" in params["required"]

    def test_execute_calls_mcp_write(self):
        """execute 正确调用 MCP Write"""
        client = make_mock_client()
        client.call_tool.return_value = {"success": True, "path": "temp/test.py", "chars_written": 20}
        tool = WriteTool(client)
        result = tool.execute(path="temp/test.py", content="print('hello')")
        client.call_tool.assert_called_once_with("Write", {"path": "temp/test.py", "content": "print('hello')", "append": False})
        parsed = json.loads(result)
        assert parsed["success"] is True

    def test_execute_append_mode(self):
        """execute 追加模式"""
        client = make_mock_client()
        client.call_tool.return_value = {"success": True, "path": "temp/log.txt", "chars_written": 5}
        tool = WriteTool(client)
        tool.execute(path="temp/log.txt", content="line2", append=True)
        client.call_tool.assert_called_once_with("Write", {"path": "temp/log.txt", "content": "line2", "append": True})

    def test_execute_readonly_rejected(self):
        """只读区域拒绝"""
        client = make_mock_client()
        client.call_tool.return_value = {"success": False, "error": "禁止写入只读区域: skills/hack.py"}
        tool = WriteTool(client)
        result = tool.execute(path="skills/hack.py", content="evil")
        assert "Error:" in result
        assert "只读区域" in result


# ============================================================================
# 4. ListTool 测试
# ============================================================================

class TestListTool:
    """ListTool 工具类测试"""

    def test_name(self):
        tool = ListTool(make_mock_client())
        assert tool.name == "List"

    def test_parameters_schema(self):
        tool = ListTool(make_mock_client())
        params = tool.parameters
        assert "path" in params["properties"]
        assert "pattern" in params["properties"]
        assert "recursive" in params["properties"]
        assert params["required"] == []

    def test_execute_calls_mcp_list(self):
        """execute 正确调用 MCP List"""
        client = make_mock_client()
        client.call_tool.return_value = {
            "success": True,
            "files": [{"name": "uploads/data.csv", "type": "file", "size": 1024}],
            "total_count": 1,
            "truncated": False
        }
        tool = ListTool(client)
        result = tool.execute(path="uploads")
        client.call_tool.assert_called_once_with("List", {"path": "uploads", "pattern": "*", "recursive": False})
        parsed = json.loads(result)
        assert parsed["success"] is True
        assert len(parsed["files"]) == 1

    def test_execute_with_pattern(self):
        """execute 传递 pattern"""
        client = make_mock_client()
        client.call_tool.return_value = {"success": True, "files": [], "total_count": 0, "truncated": False}
        tool = ListTool(client)
        tool.execute(path="uploads", pattern="*.csv", recursive=True)
        client.call_tool.assert_called_once_with("List", {"path": "uploads", "pattern": "*.csv", "recursive": True})

    def test_execute_default_params(self):
        """execute 默认参数"""
        client = make_mock_client()
        client.call_tool.return_value = {"success": True, "files": [], "total_count": 0, "truncated": False}
        tool = ListTool(client)
        tool.execute()
        client.call_tool.assert_called_once_with("List", {"path": ".", "pattern": "*", "recursive": False})


# ============================================================================
# 5. BashTool 测试
# ============================================================================

class TestBashTool:
    """BashTool 工具类测试"""

    def test_name(self):
        tool = BashTool(make_mock_client())
        assert tool.name == "Bash"

    def test_inherits_base_tool_not_mcp_base(self):
        """BashTool 继承 BaseTool，不继承 MCPToolBase"""
        tool = BashTool(make_mock_client())
        assert isinstance(tool, BaseTool)
        assert not isinstance(tool, MCPToolBase)

    def test_whitelist_python_allowed(self):
        """python 命令允许"""
        client = make_mock_client()
        client.call_tool.return_value = {"status": "completed", "exit_code": 0, "stdout": "ok", "stderr": ""}
        tool = BashTool(client)
        result = tool.execute("python temp/test.py")
        client.call_tool.assert_called_once_with("Bash", {"command": "python temp/test.py"})
        assert "ok" in result

    def test_whitelist_python3_allowed(self):
        """python3 命令允许"""
        client = make_mock_client()
        client.call_tool.return_value = {"status": "completed", "exit_code": 0, "stdout": "ok", "stderr": ""}
        tool = BashTool(client)
        result = tool.execute("python3 temp/test.py")
        client.call_tool.assert_called_once()

    def test_whitelist_cat_rejected(self):
        """cat 命令被拒绝（不再在白名单中）"""
        tool = BashTool(make_mock_client())
        result = tool.execute("cat uploads/data.csv")
        assert "Error:" in result
        assert "Only python/python3 allowed" in result

    def test_whitelist_ls_rejected(self):
        """ls 命令被拒绝"""
        tool = BashTool(make_mock_client())
        result = tool.execute("ls -la uploads/")
        assert "Error:" in result
        assert "Only python/python3 allowed" in result

    def test_whitelist_grep_rejected(self):
        """grep 命令被拒绝"""
        tool = BashTool(make_mock_client())
        result = tool.execute("grep pattern file.txt")
        assert "Error:" in result

    def test_python_c_forbidden(self):
        """python -c 被禁止"""
        tool = BashTool(make_mock_client())
        result = tool.execute('python -c "print(1)"')
        assert "Error:" in result
        assert "-c" in result or "forbidden" in result.lower()

    def test_python_m_forbidden(self):
        """python -m 被禁止"""
        tool = BashTool(make_mock_client())
        result = tool.execute("python -m http.server")
        assert "Error:" in result
        assert "-m" in result or "forbidden" in result.lower()

    def test_must_run_py_file(self):
        """必须执行 .py 文件"""
        tool = BashTool(make_mock_client())
        result = tool.execute("python somefile.txt")
        assert "Error:" in result
        assert ".py" in result

    def test_dangerous_pipe_rejected(self):
        """管道符被拒绝"""
        tool = BashTool(make_mock_client())
        result = tool.execute("python test.py | grep error")
        assert "Error:" in result
        assert "Forbidden" in result

    def test_dangerous_redirect_rejected(self):
        """重定向被拒绝"""
        tool = BashTool(make_mock_client())
        result = tool.execute("python test.py > output.txt")
        assert "Error:" in result

    def test_dangerous_semicolon_rejected(self):
        """分号被拒绝"""
        tool = BashTool(make_mock_client())
        result = tool.execute("python test.py; rm -rf /")
        assert "Error:" in result

    def test_dangerous_and_rejected(self):
        """&& 被拒绝"""
        tool = BashTool(make_mock_client())
        result = tool.execute("python test.py && rm file")
        assert "Error:" in result

    def test_empty_command(self):
        """空命令"""
        tool = BashTool(make_mock_client())
        result = tool.execute("")
        assert "Error:" in result
        assert "Empty" in result

    def test_empty_whitespace_command(self):
        """纯空白命令"""
        tool = BashTool(make_mock_client())
        result = tool.execute("   ")
        assert "Error:" in result

    def test_shlex_handles_quoted_path(self):
        """shlex.split 正确处理引号路径"""
        client = make_mock_client()
        client.call_tool.return_value = {"status": "completed", "exit_code": 0, "stdout": "ok", "stderr": ""}
        tool = BashTool(client)
        result = tool.execute('python "temp/my script.py"')
        client.call_tool.assert_called_once()

    def test_shlex_malformed_quotes(self):
        """shlex.split 处理不匹配引号"""
        tool = BashTool(make_mock_client())
        result = tool.execute('python "unclosed.py')
        assert "Error:" in result
        assert "syntax" in result.lower() or "Invalid" in result

    def test_exit_code_in_output(self):
        """非零退出码包含在输出中"""
        client = make_mock_client()
        client.call_tool.return_value = {"status": "completed", "exit_code": 1, "stdout": "fail", "stderr": "traceback"}
        tool = BashTool(client)
        result = tool.execute("python temp/test.py")
        assert "[exit_code]: 1" in result
        assert "[stderr]:" in result

    def test_no_output_returns_placeholder(self):
        """无输出时返回占位符"""
        client = make_mock_client()
        client.call_tool.return_value = {"status": "completed", "exit_code": 0, "stdout": "", "stderr": ""}
        tool = BashTool(client)
        result = tool.execute("python temp/test.py")
        assert result == "[No output]"

    def test_output_truncation(self):
        """输出二次截断保护"""
        client = make_mock_client()
        big_output = "A" * 20000 + "B" * 20000  # 40000 字符
        client.call_tool.return_value = {"status": "completed", "exit_code": 0, "stdout": big_output, "stderr": ""}
        tool = BashTool(client)
        result = tool.execute("python temp/test.py")
        assert "输出被截断" in result
        assert len(result) < len(big_output)
        # 头部应是 A，尾部应是 B
        assert result.startswith("A")
        assert result.rstrip().endswith("B")

    def test_mcp_exception_handled(self):
        """MCP 调用异常"""
        client = make_mock_client()
        client.call_tool.side_effect = TimeoutError("MCP 响应超时")
        tool = BashTool(client)
        result = tool.execute("python temp/test.py")
        assert "Error:" in result
        assert "超时" in result

    def test_description_contains_reverse_routing(self):
        """description 包含反向路由"""
        tool = BashTool(make_mock_client())
        desc = tool.description
        assert "Read" in desc
        assert "Write" in desc
        assert "List" in desc
        assert "文件操作" in desc or "专用工具" in desc


# ============================================================================
# 6. create_mcp_tools 工厂函数测试
# ============================================================================

class TestCreateMcpTools:
    """create_mcp_tools 工厂函数测试"""

    @patch('agent_system.tools.mcp_tools.MCPClient')
    @patch('agent_system.tools.mcp_tools.Config')
    def test_returns_four_tools(self, mock_config, mock_mcp_cls):
        """工厂函数返回 4 个工具"""
        mock_config.SESSIONS_ROOT = Path("/tmp/test_sessions")
        mock_config.SKILLS_DIR = Path("/tmp/test_skills")
        mock_config.DOCKER_CPUS = 1
        mock_config.DOCKER_MEMORY = "512m"
        mock_config.SANDBOX_IMAGE = "test:latest"

        tools, mcp_client = create_mcp_tools(session_id="test-session")

        assert len(tools) == 4
        names = {t.name for t in tools}
        assert names == {"Bash", "Read", "Write", "List"}
        assert mcp_client is not None

    @patch('agent_system.tools.mcp_tools.MCPClient')
    @patch('agent_system.tools.mcp_tools.Config')
    def test_all_tools_are_base_tool(self, mock_config, mock_mcp_cls):
        """所有工具都是 BaseTool 子类"""
        mock_config.SESSIONS_ROOT = Path("/tmp/test_sessions")
        mock_config.SKILLS_DIR = Path("/tmp/test_skills")

        tools, _ = create_mcp_tools(session_id="test-session")

        for tool in tools:
            assert isinstance(tool, BaseTool)

    @patch('agent_system.tools.mcp_tools.MCPClient')
    @patch('agent_system.tools.mcp_tools.Config')
    def test_no_python_tool(self, mock_config, mock_mcp_cls):
        """不应包含 PythonTool / run_python_code"""
        mock_config.SESSIONS_ROOT = Path("/tmp/test_sessions")
        mock_config.SKILLS_DIR = Path("/tmp/test_skills")

        tools, _ = create_mcp_tools(session_id="test-session")

        names = {t.name for t in tools}
        assert "run_python_code" not in names
        assert "PythonTool" not in names

    @patch('agent_system.tools.mcp_tools.MCPClient')
    @patch('agent_system.tools.mcp_tools.Config')
    def test_no_output_dir_param(self, mock_config, mock_mcp_cls):
        """create_mcp_tools 不再接受 output_dir 参数"""
        mock_config.SESSIONS_ROOT = Path("/tmp/test_sessions")
        mock_config.SKILLS_DIR = Path("/tmp/test_skills")

        import inspect
        sig = inspect.signature(create_mcp_tools)
        assert "output_dir" not in sig.parameters

    @patch('agent_system.tools.mcp_tools.MCPClient')
    @patch('agent_system.tools.mcp_tools.Config')
    def test_returns_mcp_client(self, mock_config, mock_mcp_cls):
        """工厂函数返回 MCPClient 实例"""
        mock_config.SESSIONS_ROOT = Path("/tmp/test_sessions")
        mock_config.SKILLS_DIR = Path("/tmp/test_skills")

        tools, mcp_client = create_mcp_tools(session_id="test-session")

        # mcp_client 应该是 MCPClient 的 mock 实例
        assert mcp_client is mock_mcp_cls.return_value

    @patch('agent_system.tools.mcp_tools.MCPClient')
    @patch('agent_system.tools.mcp_tools.Config')
    def test_tools_share_same_mcp_client(self, mock_config, mock_mcp_cls):
        """所有工具共享同一个 MCPClient 实例"""
        mock_config.SESSIONS_ROOT = Path("/tmp/test_sessions")
        mock_config.SKILLS_DIR = Path("/tmp/test_skills")

        tools, mcp_client = create_mcp_tools(session_id="test-session")

        for tool in tools:
            assert tool.client is mcp_client

    @patch('agent_system.tools.mcp_tools.MCPClient')
    @patch('agent_system.tools.mcp_tools.Config')
    def test_explicit_skills_dir_is_forwarded(self, mock_config, mock_mcp_cls):
        """显式 skills_dir 应覆盖默认 Config.SKILLS_DIR"""
        mock_config.SESSIONS_ROOT = Path("/tmp/test_sessions")
        mock_config.SKILLS_DIR = Path("/tmp/default_skills")

        explicit_skills_dir = Path("/tmp/bench_skills")
        create_mcp_tools(session_id="test-session", skills_dir=explicit_skills_dir)

        assert mock_mcp_cls.call_args.kwargs["skills_path"] == explicit_skills_dir


# ============================================================================
# 7. 工具 description 路由-接口验证
# ============================================================================

class TestToolDescriptions:
    """验证工具 description 的路由-接口协同"""

    def test_read_description_has_examples(self):
        tool = ReadTool(make_mock_client())
        assert "示例" in tool.description or "Read(" in tool.description

    def test_write_description_mentions_audit(self):
        tool = WriteTool(make_mock_client())
        assert "审计" in tool.description

    def test_list_description_mentions_truncation(self):
        tool = ListTool(make_mock_client())
        assert "500" in tool.description or "截断" in tool.description

    def test_bash_description_is_python_only(self):
        tool = BashTool(make_mock_client())
        desc = tool.description
        assert "python" in desc.lower()
        assert "python -c" in desc or "-c" in desc


# ============================================================================
# 入口
# ============================================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
