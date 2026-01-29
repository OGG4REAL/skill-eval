"""
配置管理模块
从环境变量加载 API keys 和系统配置
支持 DeepSeek 和 GLM 模型切换
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


class Config:
    """系统配置类"""
    
    # LLM 提供商选择 (deepseek / glm)
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").lower()
    
    # DeepSeek API 配置
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    
    # GLM API 配置（智谱官方）
    GLM_API_KEY = os.getenv("GLM_API_KEY", "")
    GLM_BASE_URL = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    GLM_MODEL = os.getenv("GLM_MODEL", "glm-4-plus")
    
    # 硅基流动 API 配置
    SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
    SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
    SILICONFLOW_MODEL = os.getenv("SILICONFLOW_MODEL", "Qwen/Qwen2.5-72B-Instruct")
    
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
    def get_llm_config(cls):
        """获取当前 LLM 配置"""
        if cls.LLM_PROVIDER == "glm":
            return {
                "api_key": cls.GLM_API_KEY,
                "base_url": cls.GLM_BASE_URL,
                "model": cls.GLM_MODEL,
                "provider": "glm"
            }
        elif cls.LLM_PROVIDER == "siliconflow":
            return {
                "api_key": cls.SILICONFLOW_API_KEY,
                "base_url": cls.SILICONFLOW_BASE_URL,
                "model": cls.SILICONFLOW_MODEL,
                "provider": "siliconflow"
            }
        else:
            return {
                "api_key": cls.DEEPSEEK_API_KEY,
                "base_url": cls.DEEPSEEK_BASE_URL,
                "model": cls.DEEPSEEK_MODEL,
                "provider": "deepseek"
            }
    
    @classmethod
    def validate(cls):
        """验证必需的配置是否存在"""
        errors = []
        
        llm_config = cls.get_llm_config()
        if not llm_config["api_key"]:
            errors.append(f"{cls.LLM_PROVIDER.upper()}_API_KEY 未设置")
        
        if errors:
            raise ValueError(f"配置错误：{', '.join(errors)}")
    
    @classmethod
    def display(cls):
        """显示当前配置（隐藏敏感信息）"""
        llm_config = cls.get_llm_config()
        api_key_display = "***" + llm_config["api_key"][-4:] if llm_config["api_key"] else "未设置"
        
        return {
            "LLM_PROVIDER": cls.LLM_PROVIDER,
            "API_KEY": api_key_display,
            "BASE_URL": llm_config["base_url"],
            "MODEL": llm_config["model"],
            "SANDBOX_IMAGE": cls.SANDBOX_IMAGE,
            "DOCKER_CPUS": cls.DOCKER_CPUS,
            "DOCKER_MEMORY": cls.DOCKER_MEMORY,
            "SKILLS_DIR": str(cls.SKILLS_DIR),
            "SESSIONS_ROOT": str(cls.SESSIONS_ROOT),
        }
