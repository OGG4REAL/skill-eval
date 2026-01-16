"""
技能加载器
从 SKILL.md 文件中提取 YAML frontmatter 元数据和完整内容
"""
import re
import yaml
from pathlib import Path
from typing import Dict, Optional, Tuple


class SkillLoader:
    """技能文件加载器"""
    
    @staticmethod
    def parse_skill_file(file_path: Path) -> Tuple[Dict, str]:
        """
        解析技能文件，提取 YAML frontmatter 和完整内容
        
        Args:
            file_path: SKILL.md 文件路径
            
        Returns:
            (元数据字典, 完整文档内容)
        """
        if not file_path.exists():
            raise FileNotFoundError(f"技能文件不存在: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 提取 YAML frontmatter（在 --- 之间）
        frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n'
        match = re.match(frontmatter_pattern, content, re.DOTALL)
        
        if match:
            frontmatter_text = match.group(1)
            try:
                metadata = yaml.safe_load(frontmatter_text)
            except yaml.YAMLError as e:
                raise ValueError(f"YAML 解析错误: {e}")
        else:
            # 如果没有 frontmatter，返回空元数据
            metadata = {}
        
        return metadata, content
    
    @staticmethod
    def extract_metadata_only(file_path: Path) -> Dict:
        """
        仅提取轻量级元数据，不读取完整内容
        
        Args:
            file_path: SKILL.md 文件路径
            
        Returns:
            元数据字典
        """
        metadata, _ = SkillLoader.parse_skill_file(file_path)
        return metadata
    
    @staticmethod
    def load_full_skill(file_path: Path) -> str:
        """
        加载完整的技能文档内容
        
        Args:
            file_path: SKILL.md 文件路径
            
        Returns:
            完整的文档内容（包括 frontmatter）
        """
        _, content = SkillLoader.parse_skill_file(file_path)
        return content
    
    @staticmethod
    def format_metadata_for_prompt(metadata: Dict) -> str:
        """
        将元数据格式化为适合放入系统提示词的字符串
        
        Args:
            metadata: 技能元数据字典
            
        Returns:
            格式化的字符串
        """
        if not metadata:
            return "无元数据"
        
        lines = []
        lines.append(f"技能名称: {metadata.get('name', '未知')}")
        lines.append(f"描述: {metadata.get('description', '无')}")
        
        if 'metadata' in metadata:
            meta_info = metadata['metadata']
            if 'version' in meta_info:
                lines.append(f"版本: {meta_info['version']}")
            if 'dependencies' in meta_info:
                lines.append(f"依赖: {meta_info['dependencies']}")
        
        return "\n".join(lines)

