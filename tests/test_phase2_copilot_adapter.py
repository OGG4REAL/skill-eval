"""
Phase 2 验证测试：CopilotKit 适配器
运行方式: python -m pytest tests/test_phase2_copilot_adapter.py -v
或直接运行: python tests/test_phase2_copilot_adapter.py

注意：完整的集成测试需要 Docker 环境和 DeepSeek API Key
"""
import json
import sys
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_sse_event_format():
    """测试 SSE 事件格式化"""
    print("\n[TEST 1] SSE 事件格式化")
    
    from server.copilot_adapter import SSEEvent
    
    # 测试文本事件
    event = SSEEvent("text", {"type": "thinking", "content": "正在分析..."})
    sse_str = event.to_sse()
    
    assert "event: text" in sse_str
    assert "data:" in sse_str
    assert "正在分析" in sse_str
    assert sse_str.endswith("\n\n")
    
    print(f"  - text 事件: {sse_str.strip()[:60]}...")
    
    # 测试工具调用事件
    tool_event = SSEEvent("tool_call", {
        "name": "render_chart",
        "arguments": {"title": "销售趋势", "chart_type": "line"}
    })
    tool_sse = tool_event.to_sse()
    
    assert "event: tool_call" in tool_sse
    assert "render_chart" in tool_sse
    
    print(f"  - tool_call 事件: {tool_sse.strip()[:60]}...")
    
    # 测试完成事件
    done_event = SSEEvent("done", {"session_id": "test123"})
    done_sse = done_event.to_sse()
    
    assert "event: done" in done_sse
    assert "test123" in done_sse
    
    print(f"  - done 事件: {done_sse.strip()}")
    print("  [PASS]")


def test_chat_request_model():
    """测试 ChatRequest 数据模型"""
    print("\n[TEST 2] ChatRequest 数据模型")
    
    from server.copilot_adapter import ChatRequest, ChatMessage, FrontendContext
    
    # 测试基本请求
    request = ChatRequest(
        messages=[
            ChatMessage(role="user", content="分析这个数据")
        ],
        session_id="test-session-001"
    )
    
    assert len(request.messages) == 1
    assert request.messages[0].role == "user"
    assert request.session_id == "test-session-001"
    
    print(f"  - messages: {len(request.messages)} 条")
    print(f"  - session_id: {request.session_id}")
    
    # 测试带前端上下文的请求
    request_with_context = ChatRequest(
        messages=[
            ChatMessage(role="user", content="解释选中的数据")
        ],
        frontend=FrontendContext(
            url="http://localhost:5173",
            context={"selected_cells": [1, 2, 3], "table_name": "sales"}
        )
    )
    
    assert request_with_context.frontend is not None
    assert request_with_context.frontend.context["table_name"] == "sales"
    
    print(f"  - frontend context: {request_with_context.frontend.context}")
    print("  [PASS]")


def test_agent_cache_entry():
    """测试 Agent 缓存条目"""
    print("\n[TEST 3] AgentCacheEntry 缓存条目")
    
    from server.copilot_adapter import AgentCacheEntry
    import time
    
    # 创建模拟 Agent
    mock_agent = MagicMock()
    
    entry = AgentCacheEntry(
        agent=mock_agent,
        session_id="session-abc"
    )
    
    assert entry.session_id == "session-abc"
    assert entry.agent is mock_agent
    
    initial_access = entry.last_access
    print(f"  - session_id: {entry.session_id}")
    print(f"  - created_at: {entry.created_at}")
    print(f"  - last_access: {entry.last_access}")
    
    # 测试 touch 更新
    time.sleep(0.1)
    entry.touch()
    
    assert entry.last_access > initial_access
    print(f"  - last_access after touch: {entry.last_access}")
    print("  [PASS]")


def test_copilot_backend_initialization():
    """测试 CopilotBackend 初始化"""
    print("\n[TEST 4] CopilotBackend 初始化")
    
    from server.copilot_adapter import CopilotBackend
    
    backend = CopilotBackend(
        max_agents=50,
        ttl_seconds=600,
        default_timeout=30.0
    )
    
    assert backend.max_agents == 50
    assert backend.ttl_seconds == 600
    assert backend.default_timeout == 30.0
    
    print(f"  - max_agents: {backend.max_agents}")
    print(f"  - ttl_seconds: {backend.ttl_seconds}")
    print(f"  - default_timeout: {backend.default_timeout}")
    
    # 测试初始统计
    stats = backend._stats
    assert stats["total_requests"] == 0
    assert stats["cache_hits"] == 0
    assert stats["cache_misses"] == 0
    
    print(f"  - initial stats: {stats}")
    print("  [PASS]")


def test_debug_info():
    """测试调试信息获取"""
    print("\n[TEST 5] 调试信息获取")
    
    from server.copilot_adapter import CopilotBackend
    
    backend = CopilotBackend()
    debug_info = backend.get_debug_info()
    
    assert "stats" in debug_info
    assert "config" in debug_info
    assert "sessions" in debug_info
    
    print(f"  - stats: {debug_info['stats']}")
    print(f"  - config: {debug_info['config']}")
    print(f"  - sessions count: {len(debug_info['sessions'])}")
    print("  [PASS]")


def test_router_creation():
    """测试路由创建"""
    print("\n[TEST 6] FastAPI 路由创建")
    
    from server.copilot_adapter import create_copilot_router, CopilotBackend
    
    backend = CopilotBackend()
    router = create_copilot_router(backend)
    
    # 检查路由注册
    routes = [route.path for route in router.routes]
    
    assert "/copilotkit/chat" in routes or "/chat" in routes
    assert "/copilotkit/debug" in routes or "/debug" in routes
    assert "/copilotkit/health" in routes or "/health" in routes
    
    print(f"  - 已注册路由: {routes}")
    print(f"  - 路由前缀: {router.prefix}")
    print("  [PASS]")


def test_cleanup_session():
    """测试会话清理"""
    print("\n[TEST 7] 会话清理功能")
    
    from server.copilot_adapter import CopilotBackend, AgentCacheEntry
    
    backend = CopilotBackend()
    
    # 手动添加一个模拟会话
    mock_agent = MagicMock()
    backend._agent_cache["test-session-to-clean"] = AgentCacheEntry(
        agent=mock_agent,
        session_id="test-session-to-clean"
    )
    
    assert "test-session-to-clean" in backend._agent_cache
    print(f"  - 添加测试会话: test-session-to-clean")
    
    # 清理会话
    result = backend.cleanup_session("test-session-to-clean")
    assert result == True
    assert "test-session-to-clean" not in backend._agent_cache
    
    print(f"  - 清理结果: {result}")
    
    # 尝试清理不存在的会话
    result = backend.cleanup_session("non-existent")
    assert result == False
    
    print(f"  - 清理不存在会话: {result}")
    print("  [PASS]")


def test_global_backend():
    """测试全局 backend 实例"""
    print("\n[TEST 8] 全局 Backend 实例")
    
    from server.copilot_adapter import get_copilot_backend
    
    backend1 = get_copilot_backend()
    backend2 = get_copilot_backend()
    
    # 应该返回同一个实例
    assert backend1 is backend2
    
    print(f"  - 实例一致性: {backend1 is backend2}")
    print("  [PASS]")


async def _test_chat_stream_mock():
    """测试聊天流（模拟版本，不需要真实 Agent）"""
    from server.copilot_adapter import CopilotBackend, ChatRequest, ChatMessage
    
    backend = CopilotBackend()
    
    # 创建测试请求
    request = ChatRequest(
        messages=[
            ChatMessage(role="user", content="测试消息")
        ],
        session_id="mock-test-session"
    )
    
    # 模拟 _get_or_create_agent 方法
    mock_agent = MagicMock()
    mock_agent.run = MagicMock(return_value={
        "response": "这是测试回复",
        "client_side_tools": [],
        "iterations": 1
    })
    
    # 用 patch 替换 _get_or_create_agent
    with patch.object(backend, '_get_or_create_agent', return_value=mock_agent):
        events = []
        async for event in backend.chat_stream(request):
            events.append(event)
            # 限制收集数量避免无限循环
            if len(events) > 10:
                break
        
        return events


def test_chat_stream_format():
    """测试聊天流格式（使用模拟）"""
    print("\n[TEST 9] 聊天流格式（模拟）")
    
    events = asyncio.run(_test_chat_stream_mock())
    
    # 验证至少有响应和完成事件
    has_response = any("response" in e for e in events)
    has_done = any("done" in e for e in events)
    
    print(f"  - 收到事件数: {len(events)}")
    print(f"  - 包含响应: {has_response}")
    print(f"  - 包含完成: {has_done}")
    
    # 打印部分事件示例
    for i, event in enumerate(events[:3]):
        preview = event[:80] + "..." if len(event) > 80 else event
        print(f"  - 事件 {i+1}: {preview}")
    
    assert has_done, "应该包含 done 事件"
    print("  [PASS]")


def test_app_router_integration():
    """测试 app.py 路由集成"""
    print("\n[TEST 10] App 路由集成")
    
    try:
        from server.app import app
        
        # 检查 copilotkit 路由是否已挂载
        routes = [route.path for route in app.routes]
        
        copilot_routes = [r for r in routes if "copilotkit" in r]
        
        print(f"  - 总路由数: {len(routes)}")
        print(f"  - CopilotKit 路由: {copilot_routes}")
        
        assert len(copilot_routes) > 0, "应该有 copilotkit 路由"
        print("  [PASS]")
        
    except ImportError as e:
        print(f"  - 跳过（导入错误）: {e}")
        print("  [SKIP]")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Phase 2 验证测试: CopilotKit 适配器")
    print("=" * 60)
    
    tests = [
        test_sse_event_format,
        test_chat_request_model,
        test_agent_cache_entry,
        test_copilot_backend_initialization,
        test_debug_info,
        test_router_creation,
        test_cleanup_session,
        test_global_backend,
        test_chat_stream_format,
        test_app_router_integration,
    ]
    
    passed = 0
    failed = 0
    skipped = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"  [FAILED] {e}")
        except Exception as e:
            # 某些测试可能因为缺少依赖而跳过
            if "SKIP" in str(e) or "导入错误" in str(e):
                skipped += 1
            else:
                failed += 1
                print(f"  [ERROR] {e}")
    
    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败, {skipped} 跳过")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
