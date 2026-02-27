"""
Token 计数器模块
使用 tiktoken + cl100k_base 编码器 + 安全系数

设计说明：
- tiktoken 是 Rust C 扩展，微秒级性能，适合在热路径调用
- cl100k_base 编码器与 GPT-4/ChatGPT 一致，对中文偏差约 10-20%
- 1.3x 安全系数保守覆盖中文文本偏差
- 预算管理不需要精确到个位数，量级正确即可
"""
import tiktoken
from typing import List, Dict, Any, Optional


class TokenCounter:
    """
    Token 计数器，用于上下文预算管理

    单例模式：避免重复加载编码器
    """

    _instance: Optional['TokenCounter'] = None
    _encoder: Optional[tiktoken.Encoding] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            try:
                cls._encoder = tiktoken.get_encoding("cl100k_base")
            except Exception as e:
                # 如果 tiktoken 不可用，使用简单的估算（1 token ≈ 4 chars）
                cls._encoder = None
        return cls._instance

    def count_text(self, text: str) -> int:
        """
        计算单个文本的 token 数量

        Args:
            text: 要计算的文本

        Returns:
            token 数量
        """
        if not text:
            return 0

        if self._encoder is not None:
            return len(self._encoder.encode(text))
        else:
            # 降级估算：1 token ≈ 4 chars（英文），中文约 2 chars
            # 使用保守估算
            return len(text) // 2

    def count_messages(self, messages: List[Dict[str, Any]], safety_factor: float = 1.3) -> int:
        """
        计算消息列表的 token 数量（含安全系数）

        估算公式参考 OpenAI 官方文档：
        - 每条消息基础开销：4 tokens（<|start|>{role}\n{content}<|end|>\n）
        - tool_calls 按内容长度计算
        - tool message 额外包含 name 字段

        Args:
            messages: OpenAI 格式的消息列表
            safety_factor: 安全系数，默认 1.3（覆盖中文偏差）

        Returns:
            估算的 token 总数
        """
        total = 0

        for msg in messages:
            # 每条消息的基础开销
            total += 4

            # content 内容
            content = msg.get("content", "")
            if content:
                total += self.count_text(content)

            # tool_calls 开销
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                for tc in tool_calls:
                    func = tc.get("function", {})
                    total += self.count_text(func.get("name", ""))
                    total += self.count_text(func.get("arguments", ""))

            # tool message 额外字段
            if msg.get("role") == "tool":
                total += self.count_text(msg.get("name", ""))
                total += self.count_text(msg.get("tool_call_id", ""))

        return int(total * safety_factor)

    def estimate_char_limit(self, token_budget: int) -> int:
        """
        根据 token 预算估算字符限制

        Args:
            token_budget: token 预算

        Returns:
            估算的字符上限（保守值）
        """
        # cl100k_base 平均约 4 chars/token（英文），中文约 2 chars/token
        # 使用保守估算
        return token_budget * 2


def get_token_counter() -> TokenCounter:
    """获取 TokenCounter 单例"""
    return TokenCounter()
