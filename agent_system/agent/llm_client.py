"""
LLM 客户端
封装 DeepSeek API（使用 OpenAI 兼容接口）
"""
from openai import OpenAI
from typing import List, Dict, Optional, Any
from ..config import Config


class LLMClient:
    """DeepSeek API 客户端封装"""
    
    def __init__(self):
        """初始化客户端"""
        self.client = OpenAI(
            api_key=Config.DEEPSEEK_API_KEY,
            base_url=Config.DEEPSEEK_BASE_URL
        )
        self.model = Config.DEEPSEEK_MODEL
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        temperature: float = None,
        max_tokens: int = None
    ) -> Dict[str, Any]:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表
            tools: 可用工具定义列表（Function Calling）
            temperature: 温度参数
            max_tokens: 最大 token 数
            
        Returns:
            API 响应字典
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or Config.TEMPERATURE,
            "max_tokens": max_tokens or Config.MAX_TOKENS,
        }
        
        # 如果提供了工具定义，添加到请求中
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        
        try:
            response = self.client.chat.completions.create(**kwargs)
            return self._parse_response(response)
        
        except Exception as e:
            raise RuntimeError(f"LLM API 调用失败: {e}")
    
    def _parse_response(self, response) -> Dict[str, Any]:
        """
        解析 API 响应
        
        Args:
            response: OpenAI API 响应对象
            
        Returns:
            解析后的字典
        """
        choice = response.choices[0]
        message = choice.message
        
        result = {
            "content": message.content,
            "role": message.role,
            "finish_reason": choice.finish_reason,
            "tool_calls": []
        }
        
        # 如果有工具调用
        if hasattr(message, 'tool_calls') and message.tool_calls:
            for tool_call in message.tool_calls:
                result["tool_calls"].append({
                    "id": tool_call.id,
                    "type": tool_call.type,
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments
                    }
                })
        
        return result
    
    def stream_chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None
    ):
        """
        流式聊天（未来扩展）
        
        Args:
            messages: 消息列表
            tools: 可用工具定义列表
            
        Yields:
            响应片段
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": Config.TEMPERATURE,
            "stream": True
        }
        
        if tools:
            kwargs["tools"] = tools
        
        try:
            stream = self.client.chat.completions.create(**kwargs)
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        
        except Exception as e:
            raise RuntimeError(f"LLM 流式调用失败: {e}")

