"""
记忆管理模块
实现对话历史的渐进式压缩和会话摘要生成

v2.0 改进：
- Skill 注入保护：识别 <skill-loaded> 标记，保护 Skill 内容不被压缩
- 多 Skill 替换：当存在多个 Skill 时，只保留最新的一个
- 区分对话轮次：按真正的用户输入划分轮次，而非思考轮次

v2.1 改进：
- Token 预算感知：压缩后检查 token 数，超预算时减少保留轮次
- 紧急截断：极端场景下的兜底机制
"""
import json
import re
from typing import List, Dict, Any, Optional

from rich.console import Console

from ..constants import (
    SKILL_LOADED_TAG,
    is_skill_injection_content,
    extract_skill_name,
)
from .token_counter import TokenCounter
from ..config import Config

# 从 Config 类获取常量
CONTEXT_TOKEN_BUDGET = Config.CONTEXT_TOKEN_BUDGET
TOKEN_SAFETY_FACTOR = Config.TOKEN_SAFETY_FACTOR


console = Console()


class MemoryManager:
    """
    对话记忆管理器

    核心功能：
    1. 滑动窗口压缩：保留最近N轮完整对话，压缩更早的历史
    2. 按时间顺序生成摘要：User → Tools → Agent 流程清晰
    3. 保留错误信息：让 LLM 从失败中学习
    4. Skill 上下文保护：识别并保护 Skill 注入消息，防止被压缩
    5. 多 Skill 替换：当加载新 Skill 时，清除旧的 Skill 内容
    """

    def __init__(self, recent_window: int = 3, recent_conversation_rounds: int = 3):
        """
        初始化记忆管理器

        Args:
            recent_window: 保留完整细节的最近思考轮数（默认3轮）- 已废弃，保留兼容
            recent_conversation_rounds: 保留完整对话轮次的数量（默认3轮）
        """
        self.recent_window = recent_window
        self.recent_conversation_rounds = recent_conversation_rounds
        self.current_round = 0  # 当前对话轮次
        self.token_counter = TokenCounter()  # Token 计数器

    # =========================================================================
    # Skill 检测方法
    # =========================================================================

    def _is_skill_injection(self, msg: Dict) -> bool:
        """
        检测是否是 Skill 注入消息（包含 <skill-loaded> 标记的 user 消息）

        Args:
            msg: 消息对象

        Returns:
            是否是 Skill 注入消息
        """
        if msg.get('role') != 'user':
            return False
        content = msg.get('content', '')
        return is_skill_injection_content(content)

    def _extract_skill_name_from_msg(self, msg: Dict) -> Optional[str]:
        """
        从 Skill 注入消息中提取技能名称

        Args:
            msg: 消息对象

        Returns:
            技能名称，如果不是 Skill 注入则返回 None
        """
        content = msg.get('content', '')
        return extract_skill_name(content)
    
    def compress_history(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        压缩对话历史，同时保护 Skill 注入内容

        核心逻辑：
        1. 分离：Skill 注入消息 vs 普通历史
        2. 多 Skill 替换：如果存在多个 Skill，只保留最新的一个
        3. Skill 注入消息始终保留，不参与压缩
        4. 对普通历史进行滑动窗口压缩（带 Token 预算感知）
        5. Token 预算检查 + 紧急截断（兜底）

        Args:
            conversation_history: 完整的对话历史

        Returns:
            压缩后的对话历史
        """
        if not conversation_history:
            return []

        # 1. 分离 Skill 注入消息和普通历史
        skill_injections = []  # [(index, skill_name, msg), ...]
        normal_history = []

        for i, msg in enumerate(conversation_history):
            if self._is_skill_injection(msg):
                skill_name = self._extract_skill_name_from_msg(msg)
                skill_injections.append((i, skill_name, msg))
            else:
                normal_history.append(msg)

        # 2. 多 Skill 替换逻辑：只保留最新的 Skill
        if len(skill_injections) > 1:
            # 只保留最后一个（最新的）
            skill_injections = [skill_injections[-1]]

        # 3. 对普通历史进行压缩（带 Token 预算感知）
        compressed_normal = self._super_compress_with_budget(normal_history)

        # 4. 重组最终上下文
        # 顺序：[压缩摘要] -> [Skill 注入] -> [最近对话]
        final_history = []

        # 摘要（如果有）
        if compressed_normal and compressed_normal[0].get('role') == 'system':
            final_history.append(compressed_normal[0])
            compressed_normal = compressed_normal[1:]

        # Skill 注入（如果有）- 始终保留在摘要之后
        for _, _, msg in skill_injections:
            final_history.append(msg)

        # 最近对话
        final_history.extend(compressed_normal)

        # 5. Token 预算检查 + 紧急截断
        total_tokens = self.token_counter.count_messages(final_history, TOKEN_SAFETY_FACTOR)
        if total_tokens > CONTEXT_TOKEN_BUDGET:
            console.print(f"[yellow]压缩后仍超预算 ({total_tokens} > {CONTEXT_TOKEN_BUDGET})，执行紧急截断[/yellow]")
            final_history = self._emergency_truncate(final_history, CONTEXT_TOKEN_BUDGET)

        return final_history

    def _super_compress(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        执行常规的滑动窗口压缩

        使用 _identify_conversation_rounds 识别真正的对话轮次，
        而非 _identify_rounds（思考轮次）。
        """
        if not conversation_history:
            return []

        # 提取现有的摘要消息
        existing_summaries = [msg for msg in conversation_history if msg.get('role') == 'system' and 'Earlier Conversation Summary' in msg.get('content', '')]

        # 识别真正的对话轮次（用户输入 → 任务完成）
        rounds = self._identify_conversation_rounds(conversation_history)

        # 如果总轮数不超过窗口大小，不压缩
        if len(rounds) <= self.recent_conversation_rounds:
            return conversation_history

        # 计算需要压缩的轮次
        compress_round_count = len(rounds) - self.recent_conversation_rounds

        # 提取需要压缩的消息和保留的消息
        compress_messages = []
        keep_messages = []

        for i, round_msgs in enumerate(rounds):
            if i < compress_round_count:
                compress_messages.extend(round_msgs)
            else:
                keep_messages.extend(round_msgs)

        # 生成新的压缩摘要
        new_summary = self._generate_compressed_summary(compress_messages, compress_round_count)

        # 合并摘要：旧摘要 + 新摘要内容
        if existing_summaries:
            combined_content = existing_summaries[0]['content'] + "\n\n" + new_summary['content']
            new_summary['content'] = combined_content

        # 返回：摘要 + 最近完整对话
        return [new_summary] + keep_messages

    def _super_compress_with_budget(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        执行滑动窗口压缩，带 Token 预算感知

        如果压缩后仍超预算，逐步减少 recent_conversation_rounds：
        - 从 3 轮 → 2 轮 → 1 轮尝试

        Args:
            conversation_history: 对话历史

        Returns:
            压缩后的对话历史
        """
        if not conversation_history:
            return []

        # 提取现有的摘要消息
        existing_summaries = [msg for msg in conversation_history if msg.get('role') == 'system' and 'Earlier Conversation Summary' in msg.get('content', '')]

        # 识别对话轮次
        rounds = self._identify_conversation_rounds(conversation_history)

        # 如果总轮数不超过窗口大小，检查是否需要压缩
        if len(rounds) <= self.recent_conversation_rounds:
            # 即使不压缩，也检查 token 预算
            tokens = self.token_counter.count_messages(conversation_history, TOKEN_SAFETY_FACTOR)
            if tokens <= CONTEXT_TOKEN_BUDGET:
                return conversation_history
            # 超预算但没有更多轮次可压缩，返回原历史（由 emergency_truncate 处理）
            return conversation_history

        # 从当前配置开始，逐步尝试减少保留轮次
        for keep_rounds in range(self.recent_conversation_rounds, 0, -1):
            if len(rounds) <= keep_rounds:
                result = conversation_history
            else:
                compress_round_count = len(rounds) - keep_rounds

                compress_messages = []
                keep_messages = []

                for i, round_msgs in enumerate(rounds):
                    if i < compress_round_count:
                        compress_messages.extend(round_msgs)
                    else:
                        keep_messages.extend(round_msgs)

                new_summary = self._generate_compressed_summary(compress_messages, compress_round_count)

                if existing_summaries:
                    combined_content = existing_summaries[0]['content'] + "\n\n" + new_summary['content']
                    new_summary['content'] = combined_content

                result = [new_summary] + keep_messages

            # 检查 token 预算
            tokens = self.token_counter.count_messages(result, TOKEN_SAFETY_FACTOR)
            if tokens <= CONTEXT_TOKEN_BUDGET:
                if keep_rounds < self.recent_conversation_rounds:
                    console.print(f"[dim]Token 预算感知：保留 {keep_rounds} 轮 ({tokens} tokens)[/dim]")
                return result

        # 如果保留 1 轮仍超预算，返回最简结果（由 emergency_truncate 处理）
        return result

    def _emergency_truncate(self, conversation_history: List[Dict[str, Any]],
                            token_budget: int) -> List[Dict[str, Any]]:
        """
        紧急截断：从最旧的非 system 消息开始删除，直到满足 token 预算

        这是最后的兜底方案，当滑动窗口压缩后仍超预算时触发。

        Args:
            conversation_history: 对话历史
            token_budget: token 预算上限

        Returns:
            截断后的对话历史（包含警告消息）
        """
        result = list(conversation_history)
        warning_msg = {
            "role": "system",
            "content": "[系统提示] 由于上下文空间不足，部分早期对话已被移除。如需引用这些内容，请重新提供。"
        }

        # 计算当前 token 数
        current_tokens = self.token_counter.count_messages(result, TOKEN_SAFETY_FACTOR)

        # 从最旧的非 system/non-skill-injection 消息开始删除
        while current_tokens > token_budget and len(result) > 1:
            # 找到第一个可删除的消息（跳过 system 和 Skill 注入）
            for i, msg in enumerate(result):
                if msg.get("role") == "system":
                    continue
                if self._is_skill_injection(msg):
                    continue
                # 找到可删除的消息
                deleted = result.pop(i)
                console.print(f"[yellow]紧急截断：删除消息 {i} (role={deleted.get('role')})[/yellow]")
                break
            else:
                # 没有可删除的消息了
                break

            current_tokens = self.token_counter.count_messages(result, TOKEN_SAFETY_FACTOR)

        # 在开头插入警告（如果实际发生了截断）
        if len(result) < len(conversation_history):
            result.insert(0, warning_msg)

        return result
    
    def _identify_rounds(self, conversation_history: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """
        识别对话轮次（旧方法，按思考轮次划分）

        每个 user 消息标志一轮对话的开始
        一轮包括：user → assistant (可能有 tool_calls) → tool (可能多个)

        注意：此方法将 Skill 注入的 user 消息也视为新一轮，可能导致错误。
        建议使用 _identify_conversation_rounds 代替。

        Args:
            conversation_history: 对话历史

        Returns:
            按轮次分组的消息列表
        """
        rounds = []
        current_round = []

        for msg in conversation_history:
            # 跳过系统消息（压缩产生的摘要）
            if msg.get('role') == 'system':
                continue

            # user 消息标志新一轮开始
            if msg.get('role') == 'user':
                if current_round:  # 保存上一轮
                    rounds.append(current_round)
                current_round = [msg]  # 开始新一轮
            else:
                current_round.append(msg)

        # 保存最后一轮
        if current_round:
            rounds.append(current_round)

        return rounds

    def _identify_conversation_rounds(self, conversation_history: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """
        识别真正的对话轮次（用户输入 → 任务完成）。

        与 _identify_rounds 不同，此方法：
        1. 将 Skill 注入的 user 消息归属到当前轮次，而非视为新一轮
        2. 正确区分"对话轮次"（用户意图）和"思考轮次"（LLM 循环）

        一轮对话包括：
        1. 用户输入（role="user"，非 Skill 注入）
        2. 可能的 Skill 注入（包含 <skill-loaded> 标记）
        3. 多轮思考（role="assistant" + tool_calls + tool）
        4. 最终回复（role="assistant"，无 tool_calls）

        Args:
            conversation_history: 对话历史

        Returns:
            按对话轮次分组的消息列表
        """
        rounds = []
        current_round = []

        for msg in conversation_history:
            # 跳过系统消息（压缩产生的摘要）
            if msg.get('role') == 'system':
                continue

            if msg.get('role') == 'user':
                # 使用 is_skill_injection_content 检测 Skill 注入
                if is_skill_injection_content(msg.get('content', '')):
                    # Skill 注入，归属到当前轮次
                    current_round.append(msg)
                else:
                    # 真正的用户输入，开始新一轮对话
                    if current_round:
                        rounds.append(current_round)
                    current_round = [msg]
            else:
                current_round.append(msg)

        # 保存最后一轮
        if current_round:
            rounds.append(current_round)

        return rounds
    
    def _generate_compressed_summary(self, messages: List[Dict[str, Any]], round_count: int) -> Dict[str, Any]:
        """
        生成压缩摘要（按时间顺序）
        
        格式：
        Round 1:
          User: [用户输入]
          Tools:
            - tool_name(args) → Success/Error: [结果]
          Agent: [助手回复]
        
        Args:
            messages: 需要压缩的消息列表
            round_count: 轮次数量
            
        Returns:
            包含压缩摘要的系统消息
        """
        # 重新按轮次组织
        # 注意：这里使用 _identify_rounds 而非 _identify_conversation_rounds 是安全的，
        # 因为 messages 参数已经经过 compress_history 过滤，不包含 Skill 注入消息。
        # 在没有 Skill 注入的情况下，两种方法的行为等价。
        rounds = self._identify_rounds(messages)
        
        summary_lines = [
            f"=== Earlier Conversation Summary (Rounds 1-{round_count}) ===",
            ""
        ]
        
        for round_idx, round_msgs in enumerate(rounds, 1):
            summary_lines.append(f"Round {round_idx}:")
            
            # 提取这一轮的各个部分
            user_msg = None
            assistant_msg = None
            tool_calls = []
            tool_results = {}
            
            for msg in round_msgs:
                if msg['role'] == 'user':
                    user_msg = msg
                elif msg['role'] == 'assistant':
                    assistant_msg = msg
                    if 'tool_calls' in msg:
                        tool_calls = msg['tool_calls']
                elif msg['role'] == 'tool':
                    tool_results[msg.get('tool_call_id')] = msg
            
            # 1. User 输入
            if user_msg:
                user_content = self._truncate_text(user_msg['content'], 100)
                summary_lines.append(f"  User: {user_content}")
            
            # 2. Tools 调用
            if tool_calls:
                summary_lines.append("  Tools:")
                for tool_call in tool_calls:
                    tool_name = tool_call['function']['name']
                    tool_args = tool_call['function']['arguments']
                    tool_id = tool_call['id']
                    
                    # 简化参数显示
                    args_str = self._format_tool_args(tool_name, tool_args)
                    summary_lines.append(f"    - {tool_name}({args_str})")
                    
                    # 显示结果
                    if tool_id in tool_results:
                        result_msg = tool_results[tool_id]
                        result_content = result_msg.get('content', '')
                        
                        # 判断是成功还是错误
                        if '错误' in result_content or 'Error' in result_content or '失败' in result_content:
                            status = "Error"
                        else:
                            status = "Success"
                        
                        result_preview = self._truncate_text(result_content, 200)
                        summary_lines.append(f"      → {status}: {result_preview}")
            else:
                summary_lines.append("  Tools: (none)")
            
            # 3. Agent 回复
            if assistant_msg and assistant_msg.get('content'):
                agent_content = self._truncate_text(assistant_msg['content'], 150)
                summary_lines.append(f"  Agent: {agent_content}")
            
            summary_lines.append("")  # 空行分隔
        
        summary_lines.append("---")
        
        return {
            "role": "system",
            "content": "\n".join(summary_lines)
        }
    
    def _format_tool_args(self, tool_name: str, args_json: str) -> str:
        """
        格式化工具参数以便显示

        Args:
            tool_name: 工具名称（PascalCase）
            args_json: 参数 JSON 字符串

        Returns:
            简化的参数字符串
        """
        try:
            args = json.loads(args_json)

            # 针对不同工具的特殊处理（使用 PascalCase）
            if tool_name == 'Bash':
                cmd = args.get('command', '')
                return f'"{cmd[:80]}..."' if len(cmd) > 80 else f'"{cmd}"'
            elif tool_name == 'Read':
                path = args.get('path', '')
                limit = args.get('limit', 2000)
                return f'path="{path}", limit={limit}'
            elif tool_name == 'Write':
                path = args.get('path', '')
                size = len(args.get('content', ''))
                return f'path="{path}", {size} chars'
            elif tool_name == 'List':
                path = args.get('path', '.')
                pattern = args.get('pattern', '*')
                return f'path="{path}", pattern="{pattern}"'
            elif tool_name == 'Skill':
                skill = args.get('skill', '')
                return f'skill="{skill}"'
            else:
                # 通用处理：只显示键名
                keys = list(args.keys())
                return f"{', '.join(keys)}"
        except:
            return "..."
    
    def _truncate_text(self, text: str, max_length: int) -> str:
        """
        截断文本
        
        Args:
            text: 原始文本
            max_length: 最大长度
            
        Returns:
            截断后的文本
        """
        if not text:
            return "(empty)"
        
        text = text.strip()
        if len(text) <= max_length:
            return text
        
        return text[:max_length] + "..."
    
    def get_session_summary(self, conversation_history: List[Dict[str, Any]]) -> str:
        """
        生成会话摘要（用于系统提示词）
        
        注意：当前实现中，摘要已经通过 compress_history 注入为 system 消息
        此方法保留用于未来扩展（如生成任务状态概览）
        
        Args:
            conversation_history: 对话历史
            
        Returns:
            会话摘要字符串
        """
        # 检查是否有压缩的摘要消息
        for msg in conversation_history:
            if msg.get('role') == 'system' and 'Earlier Conversation Summary' in msg.get('content', ''):
                # 已经有摘要，不需要额外生成
                return ""
        
        # 如果历史很短，也不需要摘要
        return ""
