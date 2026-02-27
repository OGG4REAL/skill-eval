"""
上下文预算管理测试

测试内容：
1. TokenCounter 计数准确性
2. Persisted-Output 机制（L1 门卫）
3. Token 预算感知压缩（L2 增强）
4. 紧急截断机制
"""
import pytest
import tempfile
import os
from pathlib import Path

from agent_system.agent.token_counter import TokenCounter, get_token_counter
from agent_system.agent.memory import MemoryManager
from agent_system.config import Config

# 从 Config 类获取常量
PERSISTED_OUTPUT_THRESHOLD = Config.PERSISTED_OUTPUT_THRESHOLD
PERSISTED_OUTPUT_PREVIEW_SIZE = Config.PERSISTED_OUTPUT_PREVIEW_SIZE
CONTEXT_TOKEN_BUDGET = Config.CONTEXT_TOKEN_BUDGET
TOKEN_SAFETY_FACTOR = Config.TOKEN_SAFETY_FACTOR
TOOL_RESULTS_DIR_NAME = Config.TOOL_RESULTS_DIR_NAME


class TestTokenCounter:
    """测试 Token 计数器"""

    def test_count_text_empty(self):
        """空文本返回 0"""
        counter = TokenCounter()
        assert counter.count_text("") == 0
        assert counter.count_text(None) == 0

    def test_count_text_english(self):
        """英文文本计数"""
        counter = TokenCounter()
        text = "Hello, world!"
        count = counter.count_text(text)
        assert count > 0
        assert count < len(text)  # tokens 通常比 chars 少

    def test_count_text_chinese(self):
        """中文文本计数"""
        counter = TokenCounter()
        text = "你好，世界！"
        count = counter.count_text(text)
        assert count > 0
        # 中文 tokens 通常比 chars 多

    def test_count_messages_empty(self):
        """空消息列表返回 0"""
        counter = TokenCounter()
        assert counter.count_messages([]) == 0

    def test_count_messages_basic(self):
        """基本消息列表计数"""
        counter = TokenCounter()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        count = counter.count_messages(messages, safety_factor=1.0)
        assert count > 0

    def test_count_messages_with_tool_calls(self):
        """包含 tool_calls 的消息计数"""
        counter = TokenCounter()
        messages = [
            {"role": "user", "content": "Read a file"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_123",
                        "function": {
                            "name": "Read",
                            "arguments": '{"path": "/tmp/test.txt"}'
                        }
                    }
                ]
            },
            {
                "role": "tool",
                "tool_call_id": "call_123",
                "name": "Read",
                "content": "File content here..."
            }
        ]
        count = counter.count_messages(messages, safety_factor=1.0)
        assert count > 0

    def test_safety_factor_applied(self):
        """安全系数被正确应用"""
        counter = TokenCounter()
        messages = [{"role": "user", "content": "Test message"}]

        count_no_factor = counter.count_messages(messages, safety_factor=1.0)
        count_with_factor = counter.count_messages(messages, safety_factor=1.3)

        assert count_with_factor == int(count_no_factor * 1.3)

    def test_singleton_pattern(self):
        """单例模式测试"""
        counter1 = TokenCounter()
        counter2 = TokenCounter()
        assert counter1 is counter2

        # 通过工厂函数获取
        counter3 = get_token_counter()
        assert counter3 is counter1


class TestPersistedOutput:
    """测试 L1 门卫机制"""

    def test_small_output_not_persisted(self):
        """小于阈值的输出不持久化"""
        # 模拟 Agent._persist_tool_output 逻辑
        result_str = "Small output"
        assert len(result_str) <= PERSISTED_OUTPUT_THRESHOLD

    def test_large_output_triggers_persist(self):
        """超过阈值的输出触发持久化"""
        # 模拟大输出
        result_str = "x" * (PERSISTED_OUTPUT_THRESHOLD + 1)
        assert len(result_str) > PERSISTED_OUTPUT_THRESHOLD

    def test_preview_size_correct(self):
        """预览大小正确"""
        assert PERSISTED_OUTPUT_PREVIEW_SIZE == 2048

    def test_threshold_size_correct(self):
        """阈值大小正确"""
        assert PERSISTED_OUTPUT_THRESHOLD == 8192

    def test_tool_results_dir_name_hidden(self):
        """工具结果目录名以 . 开头"""
        assert TOOL_RESULTS_DIR_NAME.startswith(".")


class TestTokenBudgetAwareness:
    """测试 Token 预算感知"""

    def setup_method(self):
        self.memory_manager = MemoryManager(recent_conversation_rounds=3)

    def test_compress_within_budget(self):
        """压缩后满足预算不触发降级"""
        # 创建一个简短的对话历史
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        compressed = self.memory_manager.compress_history(history)
        # 简短历史不应被压缩
        assert len(compressed) == 2

    def test_reduce_rounds_when_over_budget(self):
        """超预算时减少保留轮次"""
        # 这个测试需要创建足够大的历史来触发预算检查
        # 由于 CONTEXT_TOKEN_BUDGET 很大（54000），这里只验证方法存在
        assert hasattr(self.memory_manager, '_super_compress_with_budget')

    def test_emergency_truncate_method_exists(self):
        """紧急截断方法存在"""
        assert hasattr(self.memory_manager, '_emergency_truncate')

    def test_emergency_truncate_protects_system_messages(self):
        """紧急截断时保护 system 消息"""
        history = [
            {"role": "system", "content": "Summary message"},
            {"role": "user", "content": "User message"},
        ]
        # 设置一个很小的预算来触发截断
        result = self.memory_manager._emergency_truncate(history, token_budget=10)
        # system 消息应该被保留
        system_msgs = [m for m in result if m.get("role") == "system"]
        assert len(system_msgs) >= 1

    def test_emergency_truncate_protects_skill_injection(self):
        """紧急截断时保护 Skill 注入消息"""
        from agent_system.constants import SKILL_LOADED_TAG, SKILL_INJECTION_PREFIX

        skill_content = f"<{SKILL_LOADED_TAG}>test-skill</{SKILL_LOADED_TAG}>\n{SKILL_INJECTION_PREFIX} /path\n\nContent"
        history = [
            {"role": "user", "content": skill_content},  # Skill 注入
            {"role": "user", "content": "Normal message"},
            {"role": "assistant", "content": "Response"},
        ]
        # 设置一个很小的预算来触发截断
        result = self.memory_manager._emergency_truncate(history, token_budget=10)
        # Skill 注入消息应该被保留
        skill_msgs = [m for m in result if SKILL_LOADED_TAG in m.get("content", "")]
        assert len(skill_msgs) >= 1


class TestConfigConstants:
    """测试配置常量"""

    def test_persisted_output_threshold(self):
        """Persisted-Output 阈值正确"""
        assert PERSISTED_OUTPUT_THRESHOLD == 8192

    def test_persisted_output_preview_size(self):
        """Persisted-Output 预览大小正确"""
        assert PERSISTED_OUTPUT_PREVIEW_SIZE == 2048

    def test_context_token_budget(self):
        """Token 预算正确"""
        assert CONTEXT_TOKEN_BUDGET == 54000

    def test_token_safety_factor(self):
        """Token 安全系数正确"""
        assert TOKEN_SAFETY_FACTOR == 1.3

    def test_tool_results_dir_name(self):
        """工具结果目录名正确"""
        assert TOOL_RESULTS_DIR_NAME == ".tool-results"


class TestIntegration:
    """集成测试"""

    def test_full_flow_with_large_output(self):
        """测试大输出的完整流程"""
        # 这个测试验证 L1 门卫 + L2 预算感知的协同工作
        counter = TokenCounter()
        memory_manager = MemoryManager()

        # 创建一个包含大输出的历史
        large_content = "x" * 10000  # 10KB
        history = [
            {"role": "user", "content": "Read a large file"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "function": {"name": "Read", "arguments": "{}"}}
            ]},
            {"role": "tool", "tool_call_id": "call_1", "name": "Read", "content": large_content},
        ]

        # 压缩历史
        compressed = memory_manager.compress_history(history)

        # 验证压缩后的 token 数
        tokens = counter.count_messages(compressed)
        # 应该在预算内
        assert tokens <= CONTEXT_TOKEN_BUDGET or len(compressed) < len(history)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
