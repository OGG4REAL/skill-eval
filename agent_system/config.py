"""
配置管理模块
从环境变量加载 API keys 和系统配置
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


class Config:
    """系统配置类"""
    
    # DeepSeek API 配置
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    
    # 项目路径
    WORKSPACE_ROOT = Path(os.getenv("WORKSPACE_ROOT") or Path.cwd()).resolve()
    SKILLS_DIR = Path(os.getenv("SKILLS_DIR") or (WORKSPACE_ROOT / "skills")).resolve()
    SESSIONS_ROOT = Path(os.getenv("SESSIONS_ROOT") or (WORKSPACE_ROOT / "sessions")).resolve()
    SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)
    
    # 会话目录结构
    SESSION_UPLOAD_DIR_NAME = os.getenv("SESSION_UPLOAD_DIR_NAME", "uploads")
    SESSION_OUTPUT_DIR_NAME = os.getenv("SESSION_OUTPUT_DIR_NAME", "output")
    SESSION_LOG_NAME = os.getenv("SESSION_LOG_NAME", "chat.log")
    
    # Docker MCP 沙箱配置
    SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "claude-skills-sandbox:latest")
    DOCKER_CPUS = os.getenv("DOCKER_CPUS", "2")
    DOCKER_MEMORY = os.getenv("DOCKER_MEMORY", "2g")
    
    # Agent 配置
    MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "30"))
    TEMPERATURE = 0.7
    MAX_TOKENS = 4000
    
    # 语言配置
    RESPONSE_LANGUAGE = os.getenv("RESPONSE_LANGUAGE", "zh-CN")
    
    @classmethod
    def validate(cls):
        """验证必需的配置是否存在"""
        errors = []
        
        if not cls.DEEPSEEK_API_KEY:
            errors.append("DEEPSEEK_API_KEY 未设置")
        
        if errors:
            raise ValueError(f"配置错误：{', '.join(errors)}")
    
    @classmethod
    def display(cls):
        """显示当前配置（隐藏敏感信息）"""
        return {
            "DEEPSEEK_API_KEY": "***" + cls.DEEPSEEK_API_KEY[-4:] if cls.DEEPSEEK_API_KEY else "未设置",
            "DEEPSEEK_BASE_URL": cls.DEEPSEEK_BASE_URL,
            "DEEPSEEK_MODEL": cls.DEEPSEEK_MODEL,
            "SANDBOX_IMAGE": cls.SANDBOX_IMAGE,
            "DOCKER_CPUS": cls.DOCKER_CPUS,
            "DOCKER_MEMORY": cls.DOCKER_MEMORY,
            "SKILLS_DIR": str(cls.SKILLS_DIR),
            "SESSIONS_ROOT": str(cls.SESSIONS_ROOT),
        }
