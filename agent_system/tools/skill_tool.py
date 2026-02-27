"""
Skill 工具模块
实现技能加载与注入机制，对齐 Claude Code 的 Skill 工具
"""
from typing import Dict, Any
from .base import BaseTool
from ..constants import format_skill_marker


# Skill 工具 description 模板
SKILL_TOOL_DESCRIPTION_TEMPLATE = """Load a specialized skill to handle the user's task.

Skills provide domain-specific knowledge, workflows, and best practices. When a user's request matches a skill's domain, you MUST load that skill first to get detailed instructions.

CRITICAL RULES:
1. Check "Available skills" below BEFORE using Bash, Read, Write, or List tools
2. If the task matches a skill's description, call this tool IMMEDIATELY as your FIRST action
3. NEVER skip this tool and directly write code when a matching skill exists
4. After loading a skill, follow its instructions precisely

Examples:
  User: "分析 test.csv 的数据"
  → Matches "csv-data-summarizer" → Call Skill(skill="csv-data-summarizer")

  User: "帮我做一个定投收益测算"
  → Matches "fin-advisor-math" → Call Skill(skill="fin-advisor-math")

  User: "创建一个新的技能"
  → Matches "skill-creator" → Call Skill(skill="skill-creator")

How to invoke:
  Skill(skill="skill-name")
  Skill(skill="skill-name", args="optional arguments")

Available skills:
{skills_list}"""


class SkillTool(BaseTool):
    """
    Skill 工具：加载并注入技能文档到对话上下文
    
    核心机制：
    1. execute() 返回 "Launching skill: xxx"（tool 响应）
    2. get_injection_content() 返回待注入的 user 消息内容
    3. core.py 负责四步注入流程
    
    标识：skill_injector = True，用于 core.py 识别
    """
    
    # 标记为技能注入工具，core.py 会特殊处理
    skill_injector = True
    
    def __init__(self, skill_manager):
        """
        初始化 Skill 工具
        
        Args:
            skill_manager: SkillManager 实例，用于获取技能信息
        """
        self.skill_manager = skill_manager
        self._pending_skill: str = ""
        self._pending_args: str = ""
    
    @property
    def name(self) -> str:
        return "Skill"
    
    @property
    def description(self) -> str:
        """动态生成 description，包含可用技能清单"""
        skills_list = self.skill_manager.get_skills_for_tool_description()
        if not skills_list:
            skills_list = "(No skills available)"
        return SKILL_TOOL_DESCRIPTION_TEMPLATE.format(skills_list=skills_list)
    
    @property
    def parameters(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "skill": {
                    "type": "string",
                    "description": "技能名称（必须是 Available skills 中列出的技能）"
                },
                "args": {
                    "type": "string",
                    "description": "可选的技能参数",
                    "default": ""
                }
            },
            "required": ["skill"]
        }
    
    def execute(self, skill: str, args: str = "", **kwargs) -> str:
        """
        执行工具：验证技能并返回 tool 响应内容
        
        Args:
            skill: 技能名称
            args: 可选的技能参数
            
        Returns:
            str: "Launching skill: xxx" 或错误消息
        """
        # 验证技能存在
        if not self.skill_manager.get_skill_metadata(skill):
            return f"Error: Skill '{skill}' not found. Available skills: {', '.join(self.skill_manager.list_skills())}"
        
        # 缓存参数供后续注入使用
        self._pending_skill = skill
        self._pending_args = args
        
        return f"Launching skill: {skill}"
    
    def get_injection_content(self) -> str:
        """
        获取待注入的 user 消息内容

        注入格式（包含持久化标记）：
        <skill-loaded>{skill_name}</skill-loaded>
        Base directory for this skill: {skill_dir}

        {skill_content}

        ARGUMENTS: {args}

        Returns:
            str: 格式化的技能注入内容
        """
        skill_name = self._pending_skill
        skill_dir = self.skill_manager.get_skill_directory(skill_name)
        skill_content = self.skill_manager.get_skill_content(skill_name)

        # 在内容头部添加持久化标记
        skill_marker = format_skill_marker(skill_name)

        return f"""{skill_marker}Base directory for this skill: {skill_dir}

{skill_content}

ARGUMENTS: {self._pending_args or '(none)'}"""
