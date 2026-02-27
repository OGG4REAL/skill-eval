"""
MemoryManager Skill 保护功能测试

测试 Skill 注入消息的保护机制：
1. Skill 注入消息不被压缩
2. 多 Skill 替换逻辑
3. 对话轮次识别正确区分 Skill 注入和真实用户输入
"""
import pytest
from agent_system.agent.memory import MemoryManager
from agent_system.constants import (
    SKILL_LOADED_TAG,
    SKILL_INJECTION_PREFIX,
    format_skill_marker,
    is_skill_injection_content,
    extract_skill_name,
)


class TestSkillInjectionDetection:
    """测试 Skill 注入检测功能"""

    def test_is_skill_injection_content_with_marker(self):
        """测试带有 skill-loaded 标记的内容被正确识别"""
        content = f"<{SKILL_LOADED_TAG}>csv-data-summarizer</{SKILL_LOADED_TAG}>\nBase directory for this skill: /path/to/skill\n\n# Skill Content"
        assert is_skill_injection_content(content) is True

    def test_is_skill_injection_content_without_marker(self):
        """测试没有 skill-loaded 标记的内容不被识别为 Skill 注入"""
        content = "Base directory for this skill: /path/to/skill\n\n# Skill Content"
        assert is_skill_injection_content(content) is False

    def test_is_skill_injection_content_empty(self):
        """测试空内容"""
        assert is_skill_injection_content("") is False
        assert is_skill_injection_content(None) is False

    def test_is_skill_injection_content_partial_marker(self):
        """测试只有部分标记的内容不被识别"""
        content = f"<{SKILL_LOADED_TAG}>csv-data-summarizer"  # 缺少闭合标签
        assert is_skill_injection_content(content) is False

    def test_extract_skill_name_success(self):
        """测试成功提取技能名称"""
        content = f"<{SKILL_LOADED_TAG}>fin-advisor-math</{SKILL_LOADED_TAG}>\nBase directory..."
        assert extract_skill_name(content) == "fin-advisor-math"

    def test_extract_skill_name_with_hyphen(self):
        """测试提取包含连字符的技能名称"""
        content = f"<{SKILL_LOADED_TAG}>csv-data-summarizer</{SKILL_LOADED_TAG}>"
        assert extract_skill_name(content) == "csv-data-summarizer"

    def test_extract_skill_name_no_marker(self):
        """测试没有标记时返回 None"""
        content = "Base directory for this skill: /path"
        assert extract_skill_name(content) is None


class TestFormatSkillMarker:
    """测试 Skill 标记格式化"""

    def test_format_skill_marker_basic(self):
        """测试基本格式化"""
        marker = format_skill_marker("test-skill")
        expected = f"<{SKILL_LOADED_TAG}>test-skill</{SKILL_LOADED_TAG}>\n"
        assert marker == expected

    def test_format_skill_marker_with_hyphen(self):
        """测试包含连字符的技能名称"""
        marker = format_skill_marker("csv-data-summarizer")
        assert "csv-data-summarizer" in marker
        assert marker.startswith(f"<{SKILL_LOADED_TAG}>")
        assert marker.endswith("</skill-loaded>\n")


class TestMemoryManagerSkillDetection:
    """测试 MemoryManager 的 Skill 检测方法"""

    def setup_method(self):
        self.memory_manager = MemoryManager()

    def test_is_skill_injection_true(self):
        """测试 Skill 注入消息被正确识别"""
        msg = {
            "role": "user",
            "content": f"<{SKILL_LOADED_TAG}>test-skill</{SKILL_LOADED_TAG}>\n{SKILL_INJECTION_PREFIX} /path\n\nContent"
        }
        assert self.memory_manager._is_skill_injection(msg) is True

    def test_is_skill_injection_false_role(self):
        """测试非 user 角色的消息不被识别"""
        msg = {
            "role": "assistant",
            "content": f"<{SKILL_LOADED_TAG}>test-skill</{SKILL_LOADED_TAG}>"
        }
        assert self.memory_manager._is_skill_injection(msg) is False

    def test_is_skill_injection_false_content(self):
        """测试没有标记的 user 消息不被识别"""
        msg = {
            "role": "user",
            "content": "普通的用户输入"
        }
        assert self.memory_manager._is_skill_injection(msg) is False

    def test_extract_skill_name_from_msg(self):
        """测试从消息中提取技能名称"""
        msg = {
            "role": "user",
            "content": f"<{SKILL_LOADED_TAG}>my-skill</{SKILL_LOADED_TAG}>\n{SKILL_INJECTION_PREFIX} /path"
        }
        assert self.memory_manager._extract_skill_name_from_msg(msg) == "my-skill"


class TestCompressHistorySkillProtection:
    """测试 compress_history 对 Skill 注入的保护"""

    def setup_method(self):
        self.memory_manager = MemoryManager(recent_conversation_rounds=3)

    def _create_skill_injection_msg(self, skill_name: str) -> dict:
        """创建 Skill 注入消息"""
        return {
            "role": "user",
            "content": f"<{SKILL_LOADED_TAG}>{skill_name}</{SKILL_LOADED_TAG}>\n{SKILL_INJECTION_PREFIX} /path/to/{skill_name}\n\n# Skill Content"
        }

    def test_skill_injection_preserved_after_compression(self):
        """测试 Skill 注入消息在压缩后被保留"""
        # 创建历史：包含一个 Skill 注入和多个普通消息
        history = [
            {"role": "user", "content": "用户输入1"},
            {"role": "assistant", "content": "助手回复1"},
            {"role": "user", "content": "用户输入2"},
            {"role": "assistant", "content": "助手回复2"},
            self._create_skill_injection_msg("test-skill"),
            {"role": "assistant", "content": "助手回复3"},
        ]

        compressed = self.memory_manager.compress_history(history)

        # 验证 Skill 注入被保留
        skill_msgs = [msg for msg in compressed if self.memory_manager._is_skill_injection(msg)]
        assert len(skill_msgs) == 1
        assert self.memory_manager._extract_skill_name_from_msg(skill_msgs[0]) == "test-skill"

    def test_multiple_skills_only_latest_kept(self):
        """测试多个 Skill 时只保留最新的"""
        history = [
            {"role": "user", "content": "用户输入1"},
            self._create_skill_injection_msg("skill-1"),
            {"role": "assistant", "content": "助手回复1"},
            {"role": "user", "content": "用户输入2"},
            self._create_skill_injection_msg("skill-2"),
            {"role": "assistant", "content": "助手回复2"},
        ]

        compressed = self.memory_manager.compress_history(history)

        # 验证只保留了一个 Skill
        skill_msgs = [msg for msg in compressed if self.memory_manager._is_skill_injection(msg)]
        assert len(skill_msgs) == 1
        # 验证是最新的 Skill
        assert self.memory_manager._extract_skill_name_from_msg(skill_msgs[0]) == "skill-2"

    def test_no_skill_injection(self):
        """测试没有 Skill 注入时的正常压缩"""
        history = [
            {"role": "user", "content": "用户输入1"},
            {"role": "assistant", "content": "助手回复1"},
            {"role": "user", "content": "用户输入2"},
            {"role": "assistant", "content": "助手回复2"},
        ]

        compressed = self.memory_manager.compress_history(history)

        # 验证没有 Skill 注入
        skill_msgs = [msg for msg in compressed if self.memory_manager._is_skill_injection(msg)]
        assert len(skill_msgs) == 0

    def test_skill_preserved_with_actual_compression(self):
        """测试 6+ 轮对话时压缩实际发生，Skill 注入仍被保留"""
        # 创建 6 轮对话，触发压缩（recent_conversation_rounds=3）
        history = [
            # Round 1
            {"role": "user", "content": "用户输入1"},
            {"role": "assistant", "content": "助手回复1"},
            # Round 2
            {"role": "user", "content": "用户输入2"},
            {"role": "assistant", "content": "助手回复2"},
            # Round 3 - Skill 在这轮注入
            {"role": "user", "content": "用户输入3（触发技能）"},
            self._create_skill_injection_msg("csv-analyzer"),
            {"role": "assistant", "content": "助手回复3"},
            # Round 4
            {"role": "user", "content": "用户输入4"},
            {"role": "assistant", "content": "助手回复4"},
            # Round 5
            {"role": "user", "content": "用户输入5"},
            {"role": "assistant", "content": "助手回复5"},
            # Round 6
            {"role": "user", "content": "用户输入6"},
            {"role": "assistant", "content": "助手回复6"},
        ]

        compressed = self.memory_manager.compress_history(history)

        # 验证压缩发生了（结果应该比原始短）
        assert len(compressed) < len(history), "压缩应该减少消息数量"

        # 验证存在摘要
        assert compressed[0].get("role") == "system", "第一条应该是摘要"
        assert "Summary" in compressed[0].get("content", ""), "应该包含摘要"

        # 验证 Skill 注入仍然存在
        skill_msgs = [msg for msg in compressed if self.memory_manager._is_skill_injection(msg)]
        assert len(skill_msgs) == 1, "Skill 注入应该被保留"

        # 验证 Skill 位置在摘要之后
        skill_idx = next(i for i, m in enumerate(compressed) if self.memory_manager._is_skill_injection(m))
        assert skill_idx >= 1, "Skill 应该在摘要之后"


class TestIdentifyConversationRounds:
    """测试对话轮次识别"""

    def setup_method(self):
        self.memory_manager = MemoryManager()

    def _create_skill_injection_msg(self, skill_name: str) -> dict:
        """创建 Skill 注入消息"""
        return {
            "role": "user",
            "content": f"<{SKILL_LOADED_TAG}>{skill_name}</{SKILL_LOADED_TAG}>\n{SKILL_INJECTION_PREFIX} /path"
        }

    def test_skill_injection_not_start_new_round(self):
        """测试 Skill 注入不开启新一轮"""
        history = [
            {"role": "user", "content": "用户输入"},
            self._create_skill_injection_msg("test-skill"),
            {"role": "assistant", "content": "助手回复"},
        ]

        rounds = self.memory_manager._identify_conversation_rounds(history)

        # 应该只有一轮（Skill 注入归属到用户输入的轮次）
        assert len(rounds) == 1
        assert len(rounds[0]) == 3  # user + skill + assistant

    def test_real_user_input_starts_new_round(self):
        """测试真实用户输入开启新一轮"""
        history = [
            {"role": "user", "content": "用户输入1"},
            {"role": "assistant", "content": "助手回复1"},
            {"role": "user", "content": "用户输入2"},
            {"role": "assistant", "content": "助手回复2"},
        ]

        rounds = self.memory_manager._identify_conversation_rounds(history)

        # 应该有两轮
        assert len(rounds) == 2

    def test_system_message_skipped(self):
        """测试 system 消息被跳过"""
        history = [
            {"role": "system", "content": "系统消息"},
            {"role": "user", "content": "用户输入"},
            {"role": "assistant", "content": "助手回复"},
        ]

        rounds = self.memory_manager._identify_conversation_rounds(history)

        # system 消息不应计入任何轮次
        assert len(rounds) == 1
        assert len(rounds[0]) == 2  # user + assistant

    def test_complex_conversation_with_skill(self):
        """测试复杂对话（包含 Skill 注入和多轮思考）"""
        history = [
            {"role": "user", "content": "分析数据"},
            self._create_skill_injection_msg("csv-analyzer"),
            {"role": "assistant", "content": "思考1", "tool_calls": [...]},
            {"role": "tool", "content": "工具结果1"},
            {"role": "assistant", "content": "思考2", "tool_calls": [...]},
            {"role": "tool", "content": "工具结果2"},
            {"role": "assistant", "content": "最终回复"},
        ]

        rounds = self.memory_manager._identify_conversation_rounds(history)

        # 应该只有一轮对话
        assert len(rounds) == 1
        # 这轮包含所有消息
        assert len(rounds[0]) == 7


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
