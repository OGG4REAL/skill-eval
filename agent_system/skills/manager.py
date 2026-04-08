"""
技能管理器（简化版）
重构后：只负责提供元数据，不再提供"加载完整技能"的功能
"""
from pathlib import Path
from typing import Dict, List, Optional, Set
from .loader import SkillLoader


class SkillManager:
    """
    技能管理器（简化版）
    
    职责：
    1. 扫描技能目录
    2. 提取轻量级元数据（YAML frontmatter）
    3. 生成技能摘要（用于 system prompt）
    
    allowed_skills 过滤：
    - None（默认）：暴露全部扫描到的技能，即默认交互模式
    - set[str]：仅暴露指定技能，用于 benchmark variant 控制
    - 空集 set()：不暴露任何业务技能（no_skill baseline）
    """
    
    def __init__(self, skills_dir: Path, allowed_skills: Optional[Set[str]] = None):
        """
        初始化技能管理器
        
        Args:
            skills_dir: 技能目录路径
            allowed_skills: 允许暴露的技能集合。None 表示不限制。
        """
        self.skills_dir = Path(skills_dir)
        self._allowed_skills = allowed_skills
        self.skills: Dict[str, Dict] = {}  # skill_name -> {metadata, file_path, dir_path}
        self.scan_skills()
    
    def scan_skills(self):
        """扫描技能目录，加载所有技能的元数据"""
        self.skills.clear()
        
        # 查找所有 SKILL.md 文件
        skill_files = list(self.skills_dir.glob("**/SKILL.md"))
        
        for skill_file in skill_files:
            try:
                # 只提取元数据（轻量级）
                metadata = SkillLoader.extract_metadata_only(skill_file)
                skill_name = metadata.get('name', skill_file.parent.name)
                
                self.skills[skill_name] = {
                    'metadata': metadata,
                    'file_path': skill_file,
                    'dir_path': skill_file.parent
                }
                
                print(f"[SkillManager] 已索引技能: {skill_name}")
            
            except Exception as e:
                print(f"[SkillManager] 加载技能失败 {skill_file}: {e}")
        
        if self._allowed_skills is not None:
            filtered = {k: v for k, v in self.skills.items() if k in self._allowed_skills}
            removed = set(self.skills.keys()) - set(filtered.keys())
            if removed:
                print(f"[SkillManager] variant 过滤: 移除 {', '.join(sorted(removed))}")
            self.skills = filtered
    
    def get_skill_metadata(self, skill_name: str) -> Optional[Dict]:
        """
        获取技能的元数据
        
        Args:
            skill_name: 技能名称
            
        Returns:
            元数据字典，如果不存在返回 None
        """
        skill = self.skills.get(skill_name)
        return skill['metadata'] if skill else None
    
    def list_skills(self) -> List[str]:
        """
        列出所有可用的技能名称
        
        Returns:
            技能名称列表
        """
        return list(self.skills.keys())
    
    def get_skills_summary(self) -> str:
        """
        获取所有技能的简要摘要（用于系统提示词）
        
        格式：只包含 name 和 description，非常轻量级（每个约 30-50 tokens）
        
        Returns:
            格式化的技能摘要字符串
        """
        if not self.skills:
            return "No skills available."
        
        lines = []
        
        for skill_name, skill_info in self.skills.items():
            metadata = skill_info['metadata']
            description = metadata.get('description', 'No description')
            skill_path = skill_info['dir_path'].relative_to(self.skills_dir.parent)
            
            lines.append(f"### {skill_name}")
            lines.append(f"**Description**: {description}")
            lines.append(f"**Location**: `{skill_path}/SKILL.md`")
            lines.append("")
        
        return "\n".join(lines)
    
    def get_skill_directory(self, skill_name: str) -> Optional[Path]:
        """
        获取技能目录路径（供工具使用）
        
        Args:
            skill_name: 技能名称
            
        Returns:
            技能目录路径，如果不存在返回 None
        """
        skill = self.skills.get(skill_name)
        return skill['dir_path'] if skill else None
    
    def get_skills_for_tool_description(self) -> str:
        """
        返回 Skill 工具 description 所需的技能清单格式
        
        格式：简洁的列表形式，用于 Skill 工具的 description
        - skill-name-1: description
        - skill-name-2: description
        
        Returns:
            格式化的技能清单字符串
        """
        if not self.skills:
            return ""
        
        lines = []
        for skill_name, skill_info in self.skills.items():
            desc = skill_info['metadata'].get('description', 'No description')
            lines.append(f"- {skill_name}: {desc}")
        return "\n".join(lines)
    
    def get_skill_content(self, skill_name: str) -> str:
        """
        读取并返回技能的完整 SKILL.md 内容
        
        Args:
            skill_name: 技能名称
            
        Returns:
            SKILL.md 的完整内容，如果技能不存在返回错误消息
        """
        skill = self.skills.get(skill_name)
        if not skill:
            return f"Error: Skill '{skill_name}' not found"
        
        skill_file = skill['file_path']
        try:
            return skill_file.read_text(encoding='utf-8')
        except Exception as e:
            return f"Error reading skill file: {e}"
