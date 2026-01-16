"""
Phase 1 验证测试：客户端工具和 Agent Core 升级
运行方式: python -m pytest tests/test_phase1_client_side_tools.py -v
或直接运行: python tests/test_phase1_client_side_tools.py
"""
import json
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_system.tools.base import BaseTool, ToolRegistry, ClientSideToolResult
from agent_system.tools.ui_tools import (
    RenderChartTool, 
    RenderTableTool, 
    ShowNotificationTool,
    register_ui_tools,
    UI_TOOLS
)


def test_client_side_tool_result():
    """测试 ClientSideToolResult 数据类"""
    print("\n[TEST 1] ClientSideToolResult 数据类")
    
    result = ClientSideToolResult(
        tool_name="render_chart",
        arguments={"title": "销售趋势", "chart_type": "line", "data": {"labels": ["Q1", "Q2"], "datasets": []}},
        description="渲染销售趋势图"
    )
    
    assert result.tool_name == "render_chart"
    assert result.arguments["title"] == "销售趋势"
    assert "渲染销售趋势图" in result.description
    
    # 测试 to_message
    msg = result.to_message()
    assert "render_chart" in msg
    assert "已被调用" in msg or "已发送" in msg
    
    print(f"  - tool_name: {result.tool_name}")
    print(f"  - arguments: {json.dumps(result.arguments, ensure_ascii=False)}")
    print(f"  - to_message(): {msg}")
    print("  [PASS]")


def test_base_tool_client_side_attribute():
    """测试 BaseTool 的 client_side 属性"""
    print("\n[TEST 2] BaseTool client_side 属性")
    
    # 创建一个普通工具（非客户端）
    class NormalTool(BaseTool):
        @property
        def name(self): return "normal_tool"
        @property
        def description(self): return "A normal tool"
        @property
        def parameters(self): return {"type": "object", "properties": {}}
        def execute(self, **kwargs): return "done"
    
    normal = NormalTool()
    assert normal.client_side == False, "普通工具默认 client_side 应为 False"
    print(f"  - NormalTool.client_side = {normal.client_side}")
    
    # 创建一个客户端工具
    class ClientTool(BaseTool):
        client_side = True
        @property
        def name(self): return "client_tool"
        @property
        def description(self): return "A client-side tool"
        @property
        def parameters(self): return {"type": "object", "properties": {}}
        def execute(self, **kwargs): return "should not be called"
    
    client = ClientTool()
    assert client.client_side == True, "客户端工具 client_side 应为 True"
    print(f"  - ClientTool.client_side = {client.client_side}")
    print("  [PASS]")


def test_render_chart_tool():
    """测试 RenderChartTool 定义"""
    print("\n[TEST 3] RenderChartTool 工具定义")
    
    tool = RenderChartTool()
    
    assert tool.name == "render_chart"
    assert tool.client_side == True
    assert "图表" in tool.description or "chart" in tool.description.lower()
    
    # 验证参数结构
    params = tool.parameters
    assert "title" in params["properties"]
    assert "chart_type" in params["properties"]
    assert "data" in params["properties"]
    
    # 验证 chart_type 枚举
    chart_types = params["properties"]["chart_type"]["enum"]
    assert "line" in chart_types
    assert "bar" in chart_types
    assert "pie" in chart_types
    
    # 验证函数定义格式
    func_def = tool.to_function_definition()
    assert func_def["type"] == "function"
    assert func_def["function"]["name"] == "render_chart"
    
    print(f"  - name: {tool.name}")
    print(f"  - client_side: {tool.client_side}")
    print(f"  - supported chart types: {chart_types}")
    print(f"  - required params: {params.get('required', [])}")
    print("  [PASS]")


def test_tool_registry_with_client_side():
    """测试工具注册表对客户端工具的支持"""
    print("\n[TEST 4] ToolRegistry 客户端工具支持")
    
    registry = ToolRegistry()
    register_ui_tools(registry)
    
    # 验证工具已注册
    assert "render_chart" in registry.tools
    assert "render_table" in registry.tools
    assert "show_notification" in registry.tools
    
    print(f"  - 已注册工具: {list(registry.tools.keys())}")
    
    # 验证所有 UI 工具都是客户端工具
    for name, tool in registry.tools.items():
        is_client = getattr(tool, 'client_side', False)
        print(f"    - {name}: client_side={is_client}")
        assert is_client == True, f"{name} 应该是客户端工具"
    
    # 验证可以获取工具定义
    definitions = registry.get_all_definitions()
    assert len(definitions) == 3
    tool_names = [d["function"]["name"] for d in definitions]
    assert "render_chart" in tool_names
    
    print(f"  - 工具定义数量: {len(definitions)}")
    print("  [PASS]")


def test_callback_parameter():
    """测试 Agent.run 的 callback 参数（不实际运行 Agent）"""
    print("\n[TEST 5] Agent.run callback 参数签名")
    
    try:
        from agent_system.agent.core import Agent, LogCallback
        import inspect
        
        # 检查 run 方法签名
        sig = inspect.signature(Agent.run)
        params = list(sig.parameters.keys())
        
        assert "callback" in params, "run() 应该有 callback 参数"
        assert "user_input" in params
        assert "max_iterations" in params
        
        print(f"  - run() 参数: {params}")
        
        # 检查 LogCallback 类型定义
        assert LogCallback is not None
        print(f"  - LogCallback 类型已定义")
        print("  [PASS]")
    except ImportError as e:
        # 如果缺少依赖（如 rich），直接检查源文件
        print(f"  - 跳过运行时检查（缺少依赖: {e}）")
        print("  - 改为检查源代码...")
        
        core_path = Path(__file__).parent.parent / "agent_system" / "agent" / "core.py"
        source = core_path.read_text(encoding="utf-8")
        
        assert "def run(self, user_input: str" in source
        assert "callback" in source
        assert "LogCallback" in source
        assert "client_side_tool_calls" in source
        assert "ClientSideToolResult" in source
        
        print("  - run() 方法包含 callback 参数")
        print("  - LogCallback 类型已定义")
        print("  - client_side_tool_calls 收集器已添加")
        print("  [PASS]")


def test_mock_client_side_tool_execution():
    """模拟客户端工具执行流程（不实际调用 LLM）"""
    print("\n[TEST 6] 模拟客户端工具执行流程")
    
    registry = ToolRegistry()
    register_ui_tools(registry)
    
    # 模拟 Agent 检测到工具调用
    tool_name = "render_chart"
    tool_args = {
        "title": "月度销售额",
        "chart_type": "bar",
        "data": {
            "labels": ["1月", "2月", "3月"],
            "datasets": [{"name": "销售额", "values": [100, 150, 120]}]
        }
    }
    
    tool = registry.get(tool_name)
    
    # 检测是否为客户端工具
    if getattr(tool, 'client_side', False):
        # 创建 ClientSideToolResult 而非执行
        result = ClientSideToolResult(
            tool_name=tool_name,
            arguments=tool_args,
            description="前端将渲染图表"
        )
        
        print(f"  - 检测到客户端工具: {tool_name}")
        print(f"  - 跳过后端执行，创建 ClientSideToolResult")
        print(f"  - 返回给 LLM: {result.to_message()[:60]}...")
        
        # 验证结果结构
        assert result.tool_name == tool_name
        assert result.arguments == tool_args
        
        # 模拟最终返回格式
        final_result = {
            "response": "我已经为您生成了月度销售额柱状图。",
            "client_side_tools": [
                {
                    "tool_name": result.tool_name,
                    "arguments": result.arguments,
                    "description": result.description
                }
            ],
            "iterations": 1
        }
        
        print(f"  - 最终返回结构:")
        print(f"    - response: {final_result['response']}")
        print(f"    - client_side_tools: {len(final_result['client_side_tools'])} 个")
        print(f"    - iterations: {final_result['iterations']}")
        
    else:
        raise AssertionError("render_chart 应该是客户端工具")
    
    print("  [PASS]")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Phase 1 验证测试: 客户端工具和 Agent Core 升级")
    print("=" * 60)
    
    tests = [
        test_client_side_tool_result,
        test_base_tool_client_side_attribute,
        test_render_chart_tool,
        test_tool_registry_with_client_side,
        test_callback_parameter,
        test_mock_client_side_tool_execution,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  [FAILED] {e}")
    
    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
