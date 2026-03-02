"""
LLM 客户端
支持 OpenAI 兼容接口（DeepSeek / GLM / SiliconFlow）和 Anthropic 兼容接口（智谱 Coding Plan）
"""
import json
from openai import OpenAI
from typing import List, Dict, Optional, Any
from ..config import Config


class LLMClient:
    """通用 LLM API 客户端封装，自动根据 base_url 选择 OpenAI 或 Anthropic 协议"""
    
    def __init__(self):
        llm_config = Config.get_llm_config()
        
        self.provider = llm_config["provider"]
        self.model = llm_config["model"]
        self.base_url = llm_config["base_url"]
        
        self.use_anthropic = "anthropic" in self.base_url.lower()
        
        if self.use_anthropic:
            from anthropic import Anthropic
            self.client = Anthropic(
                api_key=llm_config["api_key"],
                base_url=llm_config["base_url"]
            )
            print(f"[LLMClient] 使用 {self.provider.upper()} 模型: {self.model} (Anthropic 协议)")
        else:
            self.client = OpenAI(
                api_key=llm_config["api_key"],
                base_url=llm_config["base_url"]
            )
            print(f"[LLMClient] 使用 {self.provider.upper()} 模型: {self.model} (OpenAI 协议)")
    
    # ================================================================
    # 公共接口 —— core.py 调用这两个方法，内部自动分派协议
    # ================================================================
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        temperature: float = None,
        max_tokens: int = None
    ) -> Dict[str, Any]:
        if self.use_anthropic:
            return self._chat_anthropic(messages, tools, temperature, max_tokens)
        return self._chat_openai(messages, tools, temperature, max_tokens)
    
    def stream_chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None
    ):
        if self.use_anthropic:
            yield from self._stream_anthropic(messages, tools)
        else:
            yield from self._stream_openai(messages, tools)
    
    # ================================================================
    # OpenAI 协议实现
    # ================================================================
    
    def _chat_openai(self, messages, tools=None, temperature=None, max_tokens=None):
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or Config.TEMPERATURE,
            "max_tokens": max_tokens or Config.MAX_TOKENS,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        
        try:
            response = self.client.chat.completions.create(**kwargs)
            return self._parse_openai_response(response)
        except Exception as e:
            raise RuntimeError(f"LLM API 调用失败 ({self.provider}): {e}")
    
    def _stream_openai(self, messages, tools=None):
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
            raise RuntimeError(f"LLM 流式调用失败 ({self.provider}): {e}")
    
    def _parse_openai_response(self, response) -> Dict[str, Any]:
        choice = response.choices[0]
        message = choice.message
        
        result = {
            "content": message.content,
            "role": message.role,
            "finish_reason": choice.finish_reason,
            "tool_calls": []
        }
        
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
    
    # ================================================================
    # Anthropic 协议实现
    # ================================================================
    
    def _chat_anthropic(self, messages, tools=None, temperature=None, max_tokens=None):
        system_text, anthropic_msgs = self._to_anthropic_messages(messages)
        
        kwargs = {
            "model": self.model,
            "messages": anthropic_msgs,
            "max_tokens": max_tokens or Config.MAX_TOKENS,
            "temperature": temperature or Config.TEMPERATURE,
        }
        if system_text:
            kwargs["system"] = system_text
        if tools:
            kwargs["tools"] = self._to_anthropic_tools(tools)
            kwargs["tool_choice"] = {"type": "auto"}
        
        try:
            response = self.client.messages.create(**kwargs)
            return self._parse_anthropic_response(response)
        except Exception as e:
            raise RuntimeError(f"LLM API 调用失败 ({self.provider}): {e}")
    
    def _stream_anthropic(self, messages, tools=None):
        system_text, anthropic_msgs = self._to_anthropic_messages(messages)
        
        kwargs = {
            "model": self.model,
            "messages": anthropic_msgs,
            "max_tokens": Config.MAX_TOKENS,
        }
        if system_text:
            kwargs["system"] = system_text
        if tools:
            kwargs["tools"] = self._to_anthropic_tools(tools)
        
        try:
            with self.client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as e:
            raise RuntimeError(f"LLM 流式调用失败 ({self.provider}): {e}")
    
    def _parse_anthropic_response(self, response) -> Dict[str, Any]:
        """将 Anthropic 响应转换为与 OpenAI 解析结果相同的内部格式"""
        text_parts = []
        tool_calls = []
        
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.input, ensure_ascii=False)
                    }
                })
        
        return {
            "content": "\n".join(text_parts) if text_parts else None,
            "role": "assistant",
            "finish_reason": "tool_calls" if response.stop_reason == "tool_use" else "stop",
            "tool_calls": tool_calls
        }
    
    # ================================================================
    # 格式转换辅助：OpenAI 消息 → Anthropic 消息
    # ================================================================
    
    def _to_anthropic_messages(self, messages):
        """
        从 OpenAI 格式消息列表提取 system 文本，
        并将剩余消息转换为 Anthropic 格式。
        返回 (system_text, anthropic_messages)
        """
        system_parts = []
        converted = []
        
        for msg in messages:
            role = msg["role"]
            
            if role == "system":
                system_parts.append(msg["content"])
                continue
            
            if role == "user":
                converted.append({"role": "user", "content": msg["content"]})
            
            elif role == "assistant":
                blocks = []
                text = msg.get("content")
                if text:
                    blocks.append({"type": "text", "text": text})
                
                for tc in (msg.get("tool_calls") or []):
                    func = tc["function"]
                    args = func.get("arguments", "{}")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", f"tc_{id(tc)}"),
                        "name": func["name"],
                        "input": args
                    })
                
                if not blocks:
                    blocks.append({"type": "text", "text": "."})
                converted.append({"role": "assistant", "content": blocks})
            
            elif role == "tool":
                tool_result = {
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", ""),
                    "content": msg.get("content", "")
                }
                if (converted
                        and converted[-1]["role"] == "user"
                        and isinstance(converted[-1]["content"], list)
                        and converted[-1]["content"]
                        and isinstance(converted[-1]["content"][0], dict)
                        and converted[-1]["content"][0].get("type") == "tool_result"):
                    converted[-1]["content"].append(tool_result)
                else:
                    converted.append({"role": "user", "content": [tool_result]})
        
        converted = self._ensure_alternating(converted)
        return "\n".join(system_parts).strip() or None, converted
    
    @staticmethod
    def _ensure_alternating(messages):
        """Anthropic 要求 user/assistant 严格交替"""
        if not messages:
            return messages
        
        fixed = [messages[0]]
        for msg in messages[1:]:
            if msg["role"] == fixed[-1]["role"]:
                prev_c = fixed[-1]["content"]
                cur_c = msg["content"]
                
                if isinstance(prev_c, str) and isinstance(cur_c, str):
                    fixed[-1]["content"] = prev_c + "\n" + cur_c
                elif isinstance(prev_c, list) and isinstance(cur_c, list):
                    fixed[-1]["content"] = prev_c + cur_c
                elif isinstance(prev_c, str) and isinstance(cur_c, list):
                    fixed[-1]["content"] = [{"type": "text", "text": prev_c}] + cur_c
                elif isinstance(prev_c, list) and isinstance(cur_c, str):
                    fixed[-1]["content"] = prev_c + [{"type": "text", "text": cur_c}]
            else:
                fixed.append(msg)
        
        if fixed and fixed[0]["role"] != "user":
            fixed.insert(0, {"role": "user", "content": "."})
        
        return fixed
    
    @staticmethod
    def _to_anthropic_tools(openai_tools):
        """OpenAI function-calling 工具定义 → Anthropic 工具定义"""
        return [
            {
                "name": t["function"]["name"],
                "description": t["function"].get("description", ""),
                "input_schema": t["function"].get("parameters", {"type": "object", "properties": {}})
            }
            for t in openai_tools
        ]
