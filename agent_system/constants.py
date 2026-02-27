"""
Agent System 常量定义

集中管理跨模块共享的常量，消除隐性耦合。
"""
import re

# =============================================================================
# Skill 注入相关常量
# =============================================================================

# Skill 标记标签名（用于内容标记，避免干扰 LLM）
SKILL_LOADED_TAG = "skill-loaded"

# Skill 注入内容前缀（用于检测 Skill 注入消息）
SKILL_INJECTION_PREFIX = "Base directory for this skill:"


def format_skill_marker(skill_name: str) -> str:
    """
    生成 Skill 标记头部。

    Args:
        skill_name: 技能名称

    Returns:
        标记字符串，格式：<skill-loaded>{skill_name}</skill-loaded>\n

    Example:
        >>> format_skill_marker("csv-data-summarizer")
        '<skill-loaded>csv-data-summarizer</skill-loaded>\\n'
    """
    return f"<{SKILL_LOADED_TAG}>{skill_name}</{SKILL_LOADED_TAG}>\n"


def is_skill_injection_content(content: str) -> bool:
    """
    检测消息内容是否是 Skill 注入。

    Args:
        content: 消息内容

    Returns:
        是否是 Skill 注入消息
    """
    if not content:
        return False
    return f"<{SKILL_LOADED_TAG}>" in content and f"</{SKILL_LOADED_TAG}>" in content


def extract_skill_name(content: str) -> str | None:
    """
    从 Skill 注入消息中提取技能名称。

    Args:
        content: 消息内容

    Returns:
        技能名称，如果不是 Skill 注入则返回 None
    """
    pattern = f"<{SKILL_LOADED_TAG}>(.+?)</{SKILL_LOADED_TAG}>"
    match = re.search(pattern, content)
    return match.group(1) if match else None
