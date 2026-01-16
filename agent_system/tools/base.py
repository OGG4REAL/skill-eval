"""
工具基类
定义工具接口和基础功能
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class ClientSideToolResult:
    """
    客户端工具调用结果
    
    当工具标记为 client_side=True 时，Agent 不会执行工具，
    而是返回此对象，由适配层转换为 CopilotKit 的 toolCall 指令。
    """
    tool_name: str
    arguments: Dict[str, Any]
    description: str = ""  # 可选：给 LLM 的简短说明
    
    def to_message(self) -> str:
        """转换为返回给 LLM 的消息"""
        return f"[客户端工具 '{self.tool_name}' 已被调用，参数已发送到前端进行渲染。{self.description}]"


class BaseTool(ABC):
    """工具基类"""
    
    # 标记是否为客户端工具（前端执行）
    # 如果为 True，Agent 核心将跳过 execute()，直接返回 ClientSideToolResult
    client_side: bool = False
    
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述"""
        pass
    
    @property
    @abstractmethod
    def parameters(self) -> Dict:
        """工具参数 JSON Schema"""
        pass
    
    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """
        执行工具
        
        Args:
            **kwargs: 工具参数
            
        Returns:
            执行结果
        """
        pass
    
    def to_function_definition(self) -> Dict:
        """
        转换为 OpenAI Function Calling 格式
        
        Returns:
            函数定义字典
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }


class ToolRegistry:
    """工具注册表"""
    
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool):
        """注册一个工具"""
        self.tools[tool.name] = tool
    
    def get(self, name: str) -> BaseTool:
        """获取工具"""
        return self.tools.get(name)
    
    def get_all_definitions(self) -> list:
        """获取所有工具的函数定义"""
        return [tool.to_function_definition() for tool in self.tools.values()]
    
    def execute(self, name: str, **kwargs) -> Any:
        """执行指定工具"""
        tool = self.get(name)
        if not tool:
            raise ValueError(f"工具 '{name}' 不存在")
        return tool.execute(**kwargs)

