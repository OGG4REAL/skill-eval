"""
MCP Server 原子工具单元测试

测试目标：docker-sandbox/server.py 中的 Read, Write, List, Bash
以及输出截断、安全辅助函数等。

注意：server.py 运行在 Docker 容器中，本地 venv 没有 mcp 包，
因此测试前需 mock 掉 mcp.server.fastmcp 模块。

运行方式:
    python -m pytest tests/test_mcp_server_tools.py -v
    或直接运行: python tests/test_mcp_server_tools.py
"""

import json
import importlib.util
import sys
import os
import types
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# ============================================================================
# Mock mcp 模块（本地环境没有 mcp 包，它只在 Docker 容器中）
# ============================================================================

_mock_mcp_module = types.ModuleType("mcp")
_mock_mcp_server = types.ModuleType("mcp.server")
_mock_mcp_fastmcp = types.ModuleType("mcp.server.fastmcp")


class _MockFastMCP:
    """Mock FastMCP，让 @mcp.tool() 和 @mcp.tool(name="...") 装饰器变成无操作"""
    def __init__(self, name: str):
        self.name = name

    def tool(self, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    def run(self):
        pass


_mock_mcp_fastmcp.FastMCP = _MockFastMCP
_mock_mcp_server.fastmcp = _mock_mcp_fastmcp
_mock_mcp_module.server = _mock_mcp_server

sys.modules["mcp"] = _mock_mcp_module
sys.modules["mcp.server"] = _mock_mcp_server
sys.modules["mcp.server.fastmcp"] = _mock_mcp_fastmcp

# 添加 docker-sandbox 到路径，导入 server 模块
_sandbox_server_path = Path(__file__).parent.parent / "docker-sandbox" / "server.py"
_sandbox_server_spec = importlib.util.spec_from_file_location("docker_sandbox_server", _sandbox_server_path)
assert _sandbox_server_spec and _sandbox_server_spec.loader
server = importlib.util.module_from_spec(_sandbox_server_spec)
sys.modules["docker_sandbox_server"] = server
_sandbox_server_spec.loader.exec_module(server)


# ============================================================================
# 测试基础设施
# ============================================================================

class WorkspaceFixture:
    """
    临时工作区夹具。

    创建临时目录模拟 /workspace，patch server.py 中的常量。
    """

    def __init__(self):
        self.tmpdir = None
        self.workspace = None
        self.patches = []

    def setup(self):
        self.tmpdir = tempfile.mkdtemp(prefix="mcp_test_")
        self.workspace = Path(self.tmpdir)

        # 创建标准目录结构
        (self.workspace / "uploads").mkdir()
        (self.workspace / "output").mkdir()
        (self.workspace / "skills").mkdir()
        (self.workspace / "skills" / "test-skill").mkdir(parents=True)

        # patch server 模块常量
        self.patches = [
            patch.object(server, 'WORKSPACE', self.workspace),
            patch.object(server, 'READONLY_PATHS', [self.workspace / "skills"]),
        ]
        for p in self.patches:
            p.start()

    def teardown(self):
        for p in self.patches:
            p.stop()
        if self.tmpdir and os.path.exists(self.tmpdir):
            shutil.rmtree(self.tmpdir, ignore_errors=True)

    def create_file(self, rel_path: str, content: str, encoding: str = "utf-8"):
        """在工作区中创建文件"""
        full = self.workspace / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding=encoding)
        return full

    def create_binary_file(self, rel_path: str, data: bytes):
        """在工作区中创建二进制文件"""
        full = self.workspace / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)
        return full


# 全局 fixture
fixture = WorkspaceFixture()


def setup_module():
    fixture.setup()


def teardown_module():
    fixture.teardown()


def parse(result: str) -> dict:
    """解析工具返回的 JSON 字符串"""
    return json.loads(result)


# ============================================================================
# 1. 安全辅助函数测试
# ============================================================================

class TestValidatePath:
    """_validate_path 路径校验测试"""

    def test_normal_path(self):
        result = server._validate_path("uploads/data.csv")
        assert result == fixture.workspace / "uploads" / "data.csv"

    def test_nested_path(self):
        result = server._validate_path("skills/test-skill/SKILL.md")
        assert result.is_relative_to(fixture.workspace)

    def test_current_dir(self):
        result = server._validate_path(".")
        assert result == fixture.workspace

    def test_path_traversal_rejected(self):
        """路径遍历攻击应被拒绝"""
        try:
            server._validate_path("../../etc/passwd")
            assert False, "应该抛出 ValueError"
        except ValueError as e:
            assert "路径必须在" in str(e)


class TestIsReadonly:
    """_is_readonly 只读检查测试"""

    def test_skills_is_readonly(self):
        assert server._is_readonly(fixture.workspace / "skills" / "test-skill" / "SKILL.md") is True

    def test_skills_root_is_readonly(self):
        assert server._is_readonly(fixture.workspace / "skills") is True

    def test_uploads_is_writable(self):
        assert server._is_readonly(fixture.workspace / "uploads" / "data.csv") is False

    def test_temp_is_writable(self):
        assert server._is_readonly(fixture.workspace / "temp" / "script.py") is False

    def test_output_is_writable(self):
        assert server._is_readonly(fixture.workspace / "output" / "result.json") is False


class TestCountLines:
    """_count_lines 行数统计测试"""

    def test_normal_file(self):
        path = fixture.create_file("test_count.txt", "line1\nline2\nline3\n")
        assert server._count_lines(path) == 3

    def test_no_trailing_newline(self):
        """文件末尾无换行符时也应计数最后一行"""
        path = fixture.create_file("test_no_nl.txt", "line1\nline2\nline3")
        assert server._count_lines(path) == 3

    def test_single_line_no_newline(self):
        path = fixture.create_file("test_single.txt", "hello")
        assert server._count_lines(path) == 1

    def test_single_line_with_newline(self):
        path = fixture.create_file("test_single_nl.txt", "hello\n")
        assert server._count_lines(path) == 1

    def test_empty_file(self):
        path = fixture.create_file("test_empty.txt", "")
        assert server._count_lines(path) == 0

    def test_many_lines(self):
        content = "\n".join(f"line{i}" for i in range(5000))
        path = fixture.create_file("test_many.txt", content)
        assert server._count_lines(path) == 5000


class TestTruncateOutput:
    """_truncate_output 输出截断测试"""

    def test_short_output_unchanged(self):
        text = "hello world"
        assert server._truncate_output(text) == text

    def test_exact_limit_unchanged(self):
        text = "x" * 30000
        assert server._truncate_output(text) == text

    def test_over_limit_truncated(self):
        text = "A" * 20000 + "B" * 20000  # 40000 字符
        result = server._truncate_output(text)
        assert len(result) < len(text)
        assert "输出被截断" in result
        assert result.startswith("A")
        assert result.endswith("B")

    def test_head_tail_ratio(self):
        """验证头尾保留比例"""
        text = "H" * 50000 + "T" * 50000
        result = server._truncate_output(text)
        head_size = int(server.MAX_OUTPUT_CHARS * server.HEAD_RATIO)
        assert result[:head_size] == "H" * head_size

    def test_custom_limit(self):
        text = "x" * 200
        result = server._truncate_output(text, max_chars=100)
        assert len(result) < 200
        assert "输出被截断" in result


# ============================================================================
# 2. read_file 工具测试
# ============================================================================

class TestReadFile:
    """read_file MCP 工具测试"""

    def test_basic_read(self):
        """基本文件读取"""
        fixture.create_file("uploads/hello.txt", "line1\nline2\nline3\n")
        result = parse(server.read_file("uploads/hello.txt"))
        assert result["success"] is True
        assert result["lines_read"] == 3
        assert result["total_lines"] == 3
        assert result["truncated"] is False
        assert result["encoding"] == "utf-8"
        # 检查行号格式
        assert "     1|line1" in result["content"]
        assert "     2|line2" in result["content"]
        assert "     3|line3" in result["content"]

    def test_read_with_offset(self):
        """offset 分页读取"""
        content = "\n".join(f"line{i}" for i in range(1, 11)) + "\n"
        fixture.create_file("uploads/paged.txt", content)
        result = parse(server.read_file("uploads/paged.txt", offset=5, limit=3))
        assert result["success"] is True
        assert result["lines_read"] == 3
        assert result["total_lines"] == 10
        assert result["truncated"] is True  # 5+3=8 < 10
        # 行号应从 6 开始（offset=5, 1-based）
        assert "     6|line6" in result["content"]
        assert "     8|line8" in result["content"]

    def test_read_with_limit(self):
        """limit 限制读取行数"""
        content = "\n".join(f"line{i}" for i in range(1, 101)) + "\n"
        fixture.create_file("uploads/hundred.txt", content)
        result = parse(server.read_file("uploads/hundred.txt", limit=10))
        assert result["success"] is True
        assert result["lines_read"] == 10
        assert result["total_lines"] == 100
        assert result["truncated"] is True

    def test_read_default_limit(self):
        """默认 limit=2000 的截断"""
        content = "\n".join(f"line{i}" for i in range(3000)) + "\n"
        fixture.create_file("uploads/big.txt", content)
        result = parse(server.read_file("uploads/big.txt"))
        assert result["success"] is True
        assert result["lines_read"] == 2000
        assert result["total_lines"] == 3000
        assert result["truncated"] is True

    def test_long_line_truncation(self):
        """超长行截断"""
        long_line = "x" * 3000
        fixture.create_file("uploads/longline.txt", long_line + "\n")
        result = parse(server.read_file("uploads/longline.txt"))
        assert result["success"] is True
        content = result["content"]
        assert "...[truncated]" in content
        # 行内容不应超过 MAX_LINE_CHARS + 标记长度
        line_content = content.split("|", 1)[1]
        assert len(line_content) < 3000

    def test_file_not_found(self):
        """文件不存在"""
        result = parse(server.read_file("uploads/nonexistent.csv"))
        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_path_traversal(self):
        """路径遍历攻击"""
        result = parse(server.read_file("../../etc/passwd"))
        assert result["success"] is False
        assert "路径必须在" in result["error"]

    def test_read_skills_allowed(self):
        """skills 目录可读"""
        fixture.create_file("skills/test-skill/SKILL.md", "# Test Skill\n")
        result = parse(server.read_file("skills/test-skill/SKILL.md"))
        assert result["success"] is True
        assert "Test Skill" in result["content"]

    def test_encoding_gbk_fallback(self):
        """UTF-8 失败时自动降级 GBK"""
        gbk_content = "你好世界\n测试数据\n"
        fixture.create_file("uploads/gbk.csv", gbk_content, encoding="gbk")
        result = parse(server.read_file("uploads/gbk.csv"))
        assert result["success"] is True
        assert result["encoding"] == "gbk"
        assert result["lines_read"] == 2

    def test_encoding_explicit(self):
        """显式指定编码"""
        gbk_content = "银行数据\n"
        fixture.create_file("uploads/explicit.csv", gbk_content, encoding="gbk")
        result = parse(server.read_file("uploads/explicit.csv", encoding="gbk"))
        assert result["success"] is True
        assert result["encoding"] == "gbk"

    def test_empty_file(self):
        """空文件"""
        fixture.create_file("uploads/empty.txt", "")
        result = parse(server.read_file("uploads/empty.txt"))
        assert result["success"] is True
        assert result["lines_read"] == 0
        assert result["total_lines"] == 0
        assert result["content"] == ""

    def test_read_directory_rejected(self):
        """读取目录应失败"""
        result = parse(server.read_file("uploads"))
        assert result["success"] is False
        assert "不是文件" in result["error"]

    def test_offset_beyond_file(self):
        """offset 超出文件范围"""
        fixture.create_file("uploads/short.txt", "line1\nline2\n")
        result = parse(server.read_file("uploads/short.txt", offset=100))
        assert result["success"] is True
        assert result["lines_read"] == 0
        assert result["total_lines"] == 2


# ============================================================================
# 3. write_file 工具测试
# ============================================================================

class TestWriteFile:
    """write_file MCP 工具测试"""

    def test_basic_write(self):
        """基本写入"""
        result = parse(server.write_file("output/test.txt", "hello world"))
        assert result["success"] is True
        assert result["chars_written"] > 0
        content = (fixture.workspace / "output" / "test.txt").read_text()
        assert content == "hello world"

    def test_write_creates_parent_dirs(self):
        """自动创建父目录"""
        result = parse(server.write_file("temp/sub/deep/script.py", "print('hello')"))
        assert result["success"] is True
        assert (fixture.workspace / "temp" / "sub" / "deep" / "script.py").exists()

    def test_write_overwrite(self):
        """覆盖模式"""
        server.write_file("output/overwrite.txt", "first")
        server.write_file("output/overwrite.txt", "second")
        content = (fixture.workspace / "output" / "overwrite.txt").read_text()
        assert content == "second"

    def test_write_append(self):
        """追加模式"""
        server.write_file("output/append.txt", "first\n")
        server.write_file("output/append.txt", "second\n", append=True)
        content = (fixture.workspace / "output" / "append.txt").read_text()
        assert content == "first\nsecond\n"

    def test_write_skills_rejected(self):
        """写入只读区域应被拒绝"""
        result = parse(server.write_file("skills/test-skill/hack.py", "evil code"))
        assert result["success"] is False
        assert "只读区域" in result["error"]

    def test_write_path_traversal(self):
        """路径遍历攻击"""
        result = parse(server.write_file("../../tmp/evil.sh", "rm -rf /"))
        assert result["success"] is False
        assert "路径必须在" in result["error"]

    def test_write_max_size_exceeded(self):
        """超过大小限制"""
        huge = "x" * 1_100_000
        result = parse(server.write_file("temp/huge.txt", huge))
        assert result["success"] is False
        assert "内容过大" in result["error"]

    def test_write_max_size_boundary(self):
        """恰好等于大小限制应该成功"""
        content = "x" * 1_000_000
        result = parse(server.write_file("temp/boundary.txt", content))
        assert result["success"] is True

    def test_write_returns_relative_path(self):
        """返回相对路径"""
        result = parse(server.write_file("temp/rel.txt", "test"))
        assert result["success"] is True
        path = result["path"]
        assert not Path(path).is_absolute()
        assert "temp" in path


# ============================================================================
# 4. list_files 工具测试
# ============================================================================

class TestListFiles:
    """list_files MCP 工具测试"""

    def test_list_root(self):
        """列出根目录"""
        result = parse(server.list_files("."))
        assert result["success"] is True
        assert result["total_count"] > 0
        names = [f["name"] for f in result["files"]]
        assert any("uploads" in n for n in names)

    def test_list_uploads(self):
        """列出 uploads 目录"""
        fixture.create_file("uploads/list_a.csv", "data")
        fixture.create_file("uploads/list_b.csv", "data")
        result = parse(server.list_files("uploads"))
        assert result["success"] is True
        file_names = [f["name"] for f in result["files"]]
        assert any("list_a.csv" in n for n in file_names)
        assert any("list_b.csv" in n for n in file_names)

    def test_list_with_pattern(self):
        """glob 模式匹配"""
        fixture.create_file("uploads/pattern_data.csv", "csv data")
        fixture.create_file("uploads/pattern_data.json", "json data")
        fixture.create_file("uploads/pattern_data.txt", "text data")
        result = parse(server.list_files("uploads", pattern="*.csv"))
        assert result["success"] is True
        for f in result["files"]:
            assert f["name"].endswith(".csv")

    def test_list_recursive(self):
        """递归列出"""
        fixture.create_file("skills/test-skill/SKILL.md", "# Skill")
        fixture.create_file("skills/test-skill/scripts/tool.py", "print('hi')")
        result = parse(server.list_files("skills", recursive=True))
        assert result["success"] is True
        names = [f["name"] for f in result["files"]]
        assert any("SKILL.md" in n for n in names)
        assert any("tool.py" in n for n in names)

    def test_list_file_info(self):
        """文件信息包含 type 和 size"""
        fixture.create_file("uploads/info_test.txt", "12345")
        result = parse(server.list_files("uploads", pattern="info_test.txt"))
        assert result["success"] is True
        assert len(result["files"]) >= 1
        f = [x for x in result["files"] if "info_test.txt" in x["name"]][0]
        assert f["type"] == "file"
        assert f["size"] == 5

    def test_list_nonexistent(self):
        """不存在的目录"""
        result = parse(server.list_files("no_such_dir"))
        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_list_file_as_dir(self):
        """对文件执行 list_files 应失败"""
        fixture.create_file("uploads/not_a_dir.txt", "data")
        result = parse(server.list_files("uploads/not_a_dir.txt"))
        assert result["success"] is False
        assert "不是目录" in result["error"]

    def test_list_max_results(self):
        """max_results 截断"""
        for i in range(20):
            fixture.create_file(f"uploads/batch_test/file_{i:03d}.txt", f"data{i}")
        result = parse(server.list_files("uploads/batch_test", max_results=5))
        assert result["success"] is True
        assert len(result["files"]) == 5
        assert result["total_count"] == 20
        assert result["truncated"] is True

    def test_list_path_traversal(self):
        """路径遍历攻击"""
        result = parse(server.list_files("../../"))
        assert result["success"] is False
        assert "路径必须在" in result["error"]

    def test_list_hidden_files_skipped(self):
        """隐藏文件应被跳过"""
        fixture.create_file("uploads/hidden_test/.hidden", "secret")
        fixture.create_file("uploads/hidden_test/visible.txt", "public")
        result = parse(server.list_files("uploads/hidden_test"))
        assert result["success"] is True
        names = [f["name"] for f in result["files"]]
        assert not any(".hidden" in n for n in names)
        assert any("visible.txt" in n for n in names)


# ============================================================================
# 5. exec_command 输出截断测试
# ============================================================================

class TestExecCommand:
    """exec_command 工具测试"""

    def test_basic_command(self):
        """基本命令执行"""
        fixture.create_file("temp/basic_command.py", "print('hello')")
        cmd = "python temp/basic_command.py"
        result = parse(server.exec_command(cmd))
        assert result["status"] == "completed"
        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]

    def test_command_stderr(self):
        """stderr 输出"""
        fixture.create_file("temp/stderr_command.py", "import sys\nprint('err', file=sys.stderr)")
        cmd = "python temp/stderr_command.py"
        result = parse(server.exec_command(cmd))
        assert "err" in result["stderr"]

    def test_command_exit_code(self):
        """非零退出码"""
        fixture.create_file("temp/exit_code_command.py", "raise SystemExit(42)")
        cmd = "python temp/exit_code_command.py"
        result = parse(server.exec_command(cmd))
        assert result["exit_code"] == 42

    def test_command_timeout(self):
        """命令超时"""
        fixture.create_file("temp/timeout_command.py", "import time\ntime.sleep(10)")
        cmd = "python temp/timeout_command.py"
        result = parse(server.exec_command(cmd, timeout=1))
        assert result["status"] == "timeout"

    def test_inline_python_rejected(self):
        """python -c must not reach a shell."""
        result = parse(server.exec_command('python -c "print(1)"'))
        assert result["status"] == "error"
        assert "forbidden" in result["stderr"].lower() or "-c" in result["stderr"]

    def test_stdout_truncation(self):
        """标准输出截断"""
        # 生成超过 30000 字符的输出
        fixture.create_file("temp/stdout_truncation.py", "print('A' * 20000 + 'B' * 20000)")
        fixture.create_file("temp/stdout_truncation.py", "print('A' * 20000 + 'B' * 20000)")
        cmd = "python temp/stdout_truncation.py"
        result = parse(server.exec_command(cmd))
        assert result["status"] == "completed"
        stdout = result["stdout"]
        # 原始输出 40000 字符，应被截断
        assert "输出被截断" in stdout
        # 尾部应包含 B
        assert stdout.rstrip().endswith("B")


# ============================================================================
# 6. 冻结工具验证
# ============================================================================

class TestFrozenTools:
    """验证 REPL 工具已从 MCP 工具列表中移除但函数体保留"""

    def test_run_python_exists(self):
        """run_python 函数体应保留"""
        assert hasattr(server, 'run_python')
        assert callable(server.run_python)

    def test_reset_context_exists(self):
        """reset_context 函数体应保留"""
        assert hasattr(server, 'reset_context')
        assert callable(server.reset_context)

    def test_get_context_info_exists(self):
        """get_context_info 函数体应保留"""
        assert hasattr(server, 'get_context_info')
        assert callable(server.get_context_info)

    def test_frozen_functions_still_work(self):
        """冻结的函数仍然可以直接调用（供未来 PTC 使用）"""
        # run_python
        result = json.loads(server.run_python("1 + 1"))
        assert result["success"] is True
        assert result["result"] == "2"

        # reset_context
        result = json.loads(server.reset_context())
        assert result["status"] == "ok"

        # get_context_info
        result = json.loads(server.get_context_info())
        assert result["execution_count"] == 0


# ============================================================================
# 7. 端到端场景测试
# ============================================================================

class TestEndToEnd:
    """端到端场景：模拟审计留痕工作流"""

    def test_write_then_read(self):
        """write_file 写入后 read_file 读取"""
        code = "import pandas as pd\ndf = pd.read_csv('uploads/data.csv')\nprint(df.describe())\n"
        w_result = parse(server.write_file("temp/analysis_001.py", code))
        assert w_result["success"] is True
        r_result = parse(server.read_file("temp/analysis_001.py"))
        assert r_result["success"] is True
        assert "pandas" in r_result["content"]
        assert r_result["lines_read"] == 3
        assert r_result["total_lines"] == 3

    def test_write_read_append(self):
        """写入 → 读取 → 追加 → 再读取"""
        server.write_file("temp/e2e_log.txt", "step1\n")
        server.write_file("temp/e2e_log.txt", "step2\n", append=True)
        result = parse(server.read_file("temp/e2e_log.txt"))
        assert result["success"] is True
        assert result["lines_read"] == 2
        assert "step1" in result["content"]
        assert "step2" in result["content"]

    def test_list_then_read(self):
        """list_files 发现文件后 read_file 读取"""
        fixture.create_file("uploads/scenario/report.csv", "id,name\n1,Alice\n2,Bob\n")
        l_result = parse(server.list_files("uploads/scenario"))
        assert l_result["success"] is True
        csv_files = [f for f in l_result["files"] if f["name"].endswith(".csv")]
        assert len(csv_files) >= 1
        r_result = parse(server.read_file(csv_files[0]["name"]))
        assert r_result["success"] is True
        assert "Alice" in r_result["content"]

    def test_csv_paging_workflow(self):
        """大 CSV 文件分页读取工作流"""
        header = "id,name,amount"
        rows = [f"{i},user_{i},{i*100}" for i in range(1, 5000)]
        content = header + "\n" + "\n".join(rows) + "\n"
        fixture.create_file("uploads/big_data.csv", content)
        # 第一页
        p1 = parse(server.read_file("uploads/big_data.csv", limit=100))
        assert p1["success"] is True
        assert p1["lines_read"] == 100
        assert p1["total_lines"] == 5000
        assert p1["truncated"] is True
        assert "id,name,amount" in p1["content"]
        # 第二页
        p2 = parse(server.read_file("uploads/big_data.csv", offset=100, limit=100))
        assert p2["success"] is True
        assert p2["lines_read"] == 100
        assert "   101|" in p2["content"]


# ============================================================================
# 入口
# ============================================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
