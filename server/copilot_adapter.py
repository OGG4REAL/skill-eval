"""
CopilotKit 适配器模块 (Phase 2)

实现 CopilotKit 与 Agent System 之间的桥梁。
采用 In-Process Adapter (Sidecar) 模式：
- 维护 session_id -> Agent 实例的 LRU 缓存
- 通过 SSE 协议流式返回思考过程、最终回复和客户端工具调用
- 支持回调线程安全（队列机制）
"""
import asyncio
import json
import time
import traceback
from datetime import datetime
from queue import Queue, Empty
from threading import Thread, Lock
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent_system.agent.core import Agent, LogCallback
from agent_system.skills.manager import SkillManager
from agent_system.tools import ToolRegistry, register_ui_tools, create_mcp_tools, MCPClient
from agent_system.tools.skill_tool import SkillTool
from agent_system.session import ensure_session_dirs
from agent_system.config import Config


# ============================================================================
# CleanupTTLCache - 支持过期回调的 TTL 缓存
# ============================================================================

class CleanupTTLCache(TTLCache):
    """
    支持过期回调的 TTL 缓存。
    
    在条目被移除时（TTL 过期驱逐、容量驱逐或手动删除）触发 on_expire 回调。
    回调签名：on_expire(key: str, value: Any) -> None
    
    实现细节：
    - 使用 _value_store 字典在 __setitem__ 时保存 key -> value 映射
    - 在 __delitem__ 中从 _value_store 获取 value（解决 TTL 过期时 self.get() 返回 None 的问题）
    - 重写 expire() 方法，通过 __delitem__ 清理过期项（cachetools 6.x 的 expire() 不走 __delitem__）
    - 回调在删除之后执行，确保即使回调抛异常，缓存条目也已被正确移除
    
    警告：
    - on_expire 回调可能在持有外部锁的情况下被调用（如 CopilotBackend._cache_lock）
    - 回调中绝对不能获取相同的锁，否则会死锁
    """

    def __init__(self, maxsize, ttl, on_expire=None):
        super().__init__(maxsize, ttl)
        self._on_expire = on_expire
        self._value_store: Dict[Any, Any] = {}  # 独立存储 key -> value 映射

    def __setitem__(self, key, value):
        # 先保存到独立映射表
        self._value_store[key] = value
        # 再调用父类 __setitem__（可能触发容量驱逐，驱逐时 _value_store 已有新值）
        super().__setitem__(key, value)

    def __delitem__(self, key):
        # 从独立映射表获取 value（解决 TTL 过期时 self.get() 返回 None 的问题）
        value = self._value_store.pop(key, None)
        
        # 执行实际删除
        super().__delitem__(key)
        
        # 删除成功后触发回调
        if self._on_expire and value is not None:
            try:
                self._on_expire(key, value)
            except Exception as e:
                print(f"[CleanupTTLCache] Cleanup error for {key}: {e}")

    def expire(self, time=None):
        """
        清理过期条目（重写以确保触发回调）。
        
        cachetools 6.x 的 expire() 不经过 __delitem__，而且任何对缓存的访问
        （包括 keys()、len()、__iter__）都会触发过期检查。
        
        解决方案：比较 _value_store 和实际缓存，找出被清理的 key。
        """
        # 先获取 _value_store 中所有 key 的副本（不触发过期检查）
        stored_keys = set(self._value_store.keys())
        
        # 调用父类 expire() 清理过期条目
        super().expire(time)
        
        # 比较 _value_store 和实际缓存，找出被清理的 key
        # 注意：这里使用 super().__contains__ 绕过可能的过期检查
        # 实际上直接用 TTLCache 的 __contains__ 即可，因为 expire() 已经清理完了
        for key in stored_keys:
            # 检查 key 是否还在缓存中（使用父类的 __contains__ 避免无限递归）
            if key not in self:
                # key 已被清理，触发回调
                value = self._value_store.pop(key, None)
                if self._on_expire and value is not None:
                    try:
                        self._on_expire(key, value)
                    except Exception as e:
                        print(f"[CleanupTTLCache] Cleanup error for {key}: {e}")


# ============================================================================
# 数据模型
# ============================================================================

class ChatMessage(BaseModel):
    """聊天消息"""
    role: str  # "user", "assistant", "system"
    content: str
    name: Optional[str] = None


class FrontendContext(BaseModel):
    """前端上下文"""
    url: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class ChatRequest(BaseModel):
    """聊天请求"""
    messages: List[ChatMessage]
    frontend: Optional[FrontendContext] = None
    session_id: Optional[str] = None
    max_iterations: Optional[int] = None


@dataclass
class AgentCacheEntry:
    """Agent 缓存条目"""
    agent: Agent
    session_id: str
    mcp_client: Optional[MCPClient] = None  # Phase 3: 显式持有 MCPClient 引用
    created_at: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)
    
    def touch(self):
        """更新最后访问时间"""
        self.last_access = time.time()


@dataclass
class SSEEvent:
    """SSE 事件"""
    event: str  # "text", "tool_call", "error", "done"
    data: Any
    
    def to_sse(self) -> str:
        """转换为 SSE 格式字符串"""
        data_str = json.dumps(self.data, ensure_ascii=False) if not isinstance(self.data, str) else self.data
        return f"event: {self.event}\ndata: {data_str}\n\n"


# ============================================================================
# CopilotBackend 核心类
# ============================================================================

class CopilotBackend:
    """
    CopilotKit 后端适配器
    
    职责：
    1. 管理 Agent 实例池（LRU 缓存，自动过期）
    2. 处理聊天请求，流式返回响应
    3. 将 Agent 回调转换为 SSE 事件
    """
    
    def __init__(
        self,
        max_agents: int = 100,
        ttl_seconds: int = 1800,  # 30 分钟无活动自动释放
        default_timeout: float = 600.0,  # 600 秒硬超时（10分钟，适应复杂任务）
        cleanup_interval: int = 60  # Phase 3: 过期检查间隔（秒）
    ):
        """
        初始化 CopilotBackend
        
        Args:
            max_agents: 最大缓存 Agent 数量
            ttl_seconds: Agent 缓存过期时间（秒）
            default_timeout: 默认请求超时时间（秒）
            cleanup_interval: 后台清理线程检查间隔（秒）
        """
        self.max_agents = max_agents
        self.ttl_seconds = ttl_seconds
        self.default_timeout = default_timeout
        
        # Agent 缓存（Phase 3: 使用 CleanupTTLCache，过期时自动清理容器）
        self._agent_cache: CleanupTTLCache = CleanupTTLCache(
            maxsize=max_agents,
            ttl=ttl_seconds,
            on_expire=self._cleanup_agent
        )
        self._cache_lock = Lock()
        
        # 统计信息
        self._stats = {
            "total_requests": 0,
            "active_sessions": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0
        }
        
        # Phase 3: 启动后台定时清理线程（解决 TTLCache 懒惰驱逐问题）
        self._start_cleanup_timer(cleanup_interval)

    def _start_cleanup_timer(self, interval: int):
        """
        启动后台定时清理线程。
        
        TTLCache 是懒惰驱逐——仅在访问时触发过期检查。
        此定时器定期调用 expire() 主动清理过期条目，确保容器及时释放。
        
        Args:
            interval: 检查间隔（秒），默认 60
        """
        def _periodic_expire():
            while True:
                time.sleep(interval)
                try:
                    with self._cache_lock:
                        # expire() 触发 TTLCache 内部的过期检查
                        # 过期条目会触发 _cleanup_agent 回调
                        self._agent_cache.expire()
                except Exception as e:
                    print(f"[CopilotBackend] Periodic cleanup error: {e}")
        
        t = Thread(target=_periodic_expire, daemon=True, name="cache-cleanup")
        t.start()

    def _cleanup_agent(self, session_id: str, entry: AgentCacheEntry):
        """
        Agent 过期时清理资源（由 CleanupTTLCache 触发）。
        
        ⚠️ 此方法在 _cache_lock 内执行，绝对不能再获取 _cache_lock，否则死锁！
        """
        print(f"[CopilotBackend] Cleaning up session: {session_id}")
        
        # 1. 清理 MCP 客户端（停止 Docker 容器）— 必须先停容器再删文件
        if entry.mcp_client:
            try:
                entry.mcp_client.cleanup()
                print(f"[CopilotBackend] MCP container stopped for {session_id}")
            except Exception as e:
                print(f"[CopilotBackend] MCP cleanup error for {session_id}: {e}")
        
        # 2. 清理临时文件（容器已停止，不会有文件锁冲突）
        self._cleanup_temp_files(session_id)

    def _cleanup_temp_files(self, session_id: str):
        """清理会话的临时脚本文件（审计留痕目录）"""
        import shutil
        temp_dir = Config.SESSIONS_ROOT / session_id / "temp"
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"[CopilotBackend] Cleaned temp files for {session_id}")
        
    def _get_or_create_agent(self, session_id: str) -> Agent:
        """
        获取或创建 Agent 实例
        
        Args:
            session_id: 会话 ID
            
        Returns:
            Agent 实例
        """
        with self._cache_lock:
            if session_id in self._agent_cache:
                entry = self._agent_cache[session_id]
                entry.touch()
                self._stats["cache_hits"] += 1
                return entry.agent
            
            self._stats["cache_misses"] += 1
        
        # 创建新的 Agent 实例（在锁外执行，避免阻塞）
        agent, mcp_client = self._create_agent(session_id)
        
        with self._cache_lock:
            # 双重检查
            if session_id not in self._agent_cache:
                self._agent_cache[session_id] = AgentCacheEntry(
                    agent=agent,
                    session_id=session_id,
                    mcp_client=mcp_client,  # Phase 3: 保存 MCPClient 引用
                )
                self._stats["active_sessions"] = len(self._agent_cache)
            else:
                # 另一个线程已创建，清理本次多余的 mcp_client
                if mcp_client:
                    mcp_client.cleanup()
                agent = self._agent_cache[session_id].agent
        
        return agent
    
    def _create_agent(self, session_id: str) -> Tuple[Agent, MCPClient]:
        """
        创建新的 Agent 实例
        
        Args:
            session_id: 会话 ID
            
        Returns:
            (agent, mcp_client) 元组
        """
        # 确保会话目录存在
        base_dir, uploads_dir, output_dir, log_file = ensure_session_dirs(session_id)
        
        # 初始化技能管理器
        skill_manager = SkillManager(Config.SKILLS_DIR)
        
        # 初始化工具注册表
        tool_registry = ToolRegistry()
        
        # 注册 Skill 工具（优先级最高，放在最前面）
        skill_tool = SkillTool(skill_manager)
        tool_registry.register(skill_tool)
        
        # 注册 UI 工具（客户端工具）
        register_ui_tools(tool_registry)
        
        # 注册 MCP 工具（Bash, Read, Write, List）
        mcp_tools, mcp_client = create_mcp_tools(
            uploads_dir=str(uploads_dir),
        )
        for tool in mcp_tools:
            tool_registry.register(tool)
        
        # 创建 Agent
        agent = Agent(
            skill_manager=skill_manager,
            tool_registry=tool_registry,
            log_file=str(log_file),
            uploads_dir=str(uploads_dir)
        )
        
        return agent, mcp_client
    
    async def chat_stream(
        self,
        request: ChatRequest
    ) -> AsyncGenerator[str, None]:
        """
        处理聊天请求，流式返回 SSE 事件
        
        Args:
            request: 聊天请求
            
        Yields:
            SSE 格式的事件字符串
        """
        self._stats["total_requests"] += 1
        
        # 获取或生成 session_id
        session_id = request.session_id
        if not session_id:
            from uuid import uuid4
            session_id = uuid4().hex
        
        # 提取用户最新消息
        user_message = ""
        for msg in reversed(request.messages):
            if msg.role == "user":
                user_message = msg.content
                break
        
        if not user_message:
            yield SSEEvent("error", {"message": "没有找到用户消息"}).to_sse()
            yield SSEEvent("done", {}).to_sse()
            return
        
        # 创建事件队列用于线程间通信
        event_queue: Queue[SSEEvent] = Queue()
        
        # 定义回调函数（在 Agent 线程中调用）
        def agent_callback(event_type: str, message: str):
            """Agent 日志回调 -> SSE 事件"""
            if event_type == "thinking":
                event_queue.put(SSEEvent("text", {"type": "thinking", "content": message}))
            elif event_type == "tool_call":
                event_queue.put(SSEEvent("text", {"type": "tool_call", "content": message}))
            elif event_type == "tool_result":
                event_queue.put(SSEEvent("text", {"type": "tool_result", "content": message}))
            elif event_type == "client_side_tool":
                # 客户端工具调用 - 特殊处理
                try:
                    tool_data = json.loads(message)
                    event_queue.put(SSEEvent("tool_call", tool_data))
                except json.JSONDecodeError:
                    event_queue.put(SSEEvent("text", {"type": "client_side_tool", "content": message}))
            elif event_type == "error":
                event_queue.put(SSEEvent("error", {"message": message}))
        
        # 运行结果容器
        result_container: Dict[str, Any] = {"result": None, "error": None}
        
        def run_agent():
            """在线程中运行 Agent"""
            try:
                agent = self._get_or_create_agent(session_id)
                
                # 构建完整的用户输入（包含前端上下文）
                full_input = user_message
                if request.frontend and request.frontend.context:
                    context_str = json.dumps(request.frontend.context, ensure_ascii=False, indent=2)
                    full_input = f"{user_message}\n\n[前端上下文]\n{context_str}"
                
                # 运行 Agent
                result = agent.run(
                    user_input=full_input,
                    max_iterations=request.max_iterations or Config.MAX_ITERATIONS,
                    callback=agent_callback
                )
                
                result_container["result"] = result
                
            except Exception as e:
                result_container["error"] = str(e)
                event_queue.put(SSEEvent("error", {"message": str(e), "traceback": traceback.format_exc()}))
            finally:
                # 标记完成
                event_queue.put(None)
        
        # 在线程池中运行 Agent
        agent_thread = Thread(target=run_agent, daemon=True)
        agent_thread.start()
        
        # 流式返回事件
        timeout = self.default_timeout
        start_time = time.time()
        
        try:
            while True:
                # 检查超时
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    yield SSEEvent("error", {"message": f"请求超时（{timeout}秒）"}).to_sse()
                    break
                
                try:
                    event = event_queue.get(timeout=0.1)
                    
                    if event is None:
                        # Agent 完成
                        break
                    
                    yield event.to_sse()
                    
                except Empty:
                    # 发送心跳保持连接
                    if elapsed % 10 < 0.2:  # 每 10 秒发送一次心跳
                        yield SSEEvent("heartbeat", {"elapsed": int(elapsed)}).to_sse()
                    await asyncio.sleep(0.05)
        
        except asyncio.CancelledError:
            # 客户端断开连接
            pass
        
        # 处理最终结果
        result = result_container.get("result")
        error = result_container.get("error")
        
        if error:
            self._stats["errors"] += 1
            yield SSEEvent("error", {"message": error}).to_sse()
        elif result:
            # 发送最终回复
            yield SSEEvent("text", {
                "type": "response",
                "content": result.get("response", ""),
                "iterations": result.get("iterations", 0)
            }).to_sse()
        
        # 发送完成事件
        yield SSEEvent("done", {"session_id": session_id}).to_sse()
    
    def get_debug_info(self) -> Dict[str, Any]:
        """
        获取调试信息
        
        Returns:
            包含统计和会话信息的字典
        """
        with self._cache_lock:
            sessions = []
            for session_id, entry in self._agent_cache.items():
                sessions.append({
                    "session_id": session_id,
                    "created_at": datetime.fromtimestamp(entry.created_at).isoformat(),
                    "last_access": datetime.fromtimestamp(entry.last_access).isoformat(),
                    "age_seconds": int(time.time() - entry.created_at),
                    "idle_seconds": int(time.time() - entry.last_access)
                })
            
            self._stats["active_sessions"] = len(sessions)
        
        return {
            "stats": self._stats.copy(),
            "config": {
                "max_agents": self.max_agents,
                "ttl_seconds": self.ttl_seconds,
                "default_timeout": self.default_timeout
            },
            "sessions": sessions
        }
    
    def cleanup_session(self, session_id: str) -> bool:
        """
        手动清理指定会话
        
        Args:
            session_id: 会话 ID
            
        Returns:
            是否成功清理
        """
        with self._cache_lock:
            if session_id in self._agent_cache:
                del self._agent_cache[session_id]
                self._stats["active_sessions"] = len(self._agent_cache)
                return True
        return False


# ============================================================================
# FastAPI 路由
# ============================================================================

def create_copilot_router(backend: Optional[CopilotBackend] = None) -> APIRouter:
    """
    创建 CopilotKit 路由
    
    Args:
        backend: CopilotBackend 实例，如果为 None 则创建新实例
        
    Returns:
        FastAPI APIRouter
    """
    router = APIRouter(prefix="/copilotkit", tags=["CopilotKit"])
    
    # 使用传入的 backend 或创建新的
    _backend = backend or CopilotBackend()
    
    @router.get("/chat/info")
    async def info():
        """
        CopilotKit 信息端点
        
        返回运行时信息和可用 agents
        """
        return {
            "agents": [
                {
                    "name": "default",
                    "description": "CSV Data Summarizer Agent - AI驱动的数据分析助手"
                }
            ],
            "coagents": [],
            "actions": [
                {
                    "name": "render_chart",
                    "description": "在前端渲染交互式图表",
                    "parameters": []
                },
                {
                    "name": "render_table",
                    "description": "在前端渲染交互式表格",
                    "parameters": []
                },
                {
                    "name": "show_notification",
                    "description": "显示通知提示",
                    "parameters": []
                }
            ]
        }
    
    @router.post("/chat")
    async def chat(request: ChatRequest):
        """
        聊天接口（SSE 流式响应）
        
        协议规范:
        - event: text -> 思考过程和最终回复
        - event: tool_call -> 客户端工具调用
        - event: error -> 错误信息
        - event: done -> 完成标志
        """
        return StreamingResponse(
            _backend.chat_stream(request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # 禁用 Nginx 缓冲
            }
        )
    
    @router.get("/debug")
    async def debug():
        """
        调试接口
        
        返回活跃会话列表和统计信息
        """
        return _backend.get_debug_info()
    
    @router.delete("/sessions/{session_id}")
    async def cleanup_session(session_id: str):
        """
        清理指定会话
        """
        success = _backend.cleanup_session(session_id)
        if success:
            return {"status": "ok", "message": f"会话 {session_id} 已清理"}
        else:
            raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")
    
    @router.get("/health")
    async def health():
        """
        健康检查接口
        """
        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat()
        }
    
    return router


# 全局 backend 实例（懒加载）
_global_backend: Optional[CopilotBackend] = None


def get_copilot_backend() -> CopilotBackend:
    """获取全局 CopilotBackend 实例"""
    global _global_backend
    if _global_backend is None:
        _global_backend = CopilotBackend()
    return _global_backend
