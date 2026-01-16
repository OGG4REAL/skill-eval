"""
记忆管理模块
实现对话历史的渐进式压缩和会话摘要生成
"""
import json
from typing import List, Dict, Any, Optional


class MemoryManager:
    """
    对话记忆管理器
    
    核心功能：
    1. 滑动窗口压缩：保留最近N轮完整对话，压缩更早的历史
    2. 按时间顺序生成摘要：User → Tools → Agent 流程清晰
    3. 保留错误信息：让 LLM 从失败中学习
    4. Skill 上下文保护：识别并保护 Skill 文档交互，防止被压缩
    """
    
    def __init__(self, recent_window: int = 3):
        """
        初始化记忆管理器
        
        Args:
            recent_window: 保留完整细节的最近轮数（默认3轮）
        """
        self.recent_window = recent_window
        self.current_round = 0  # 当前对话轮次
    
    def compress_history(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        压缩对话历史，同时保护 Skill 文档
        """
        if not conversation_history:
            return []
        
        # 1. 分离：提取 Skill 文档相关的交互
        skill_interactions = [] # 存放 (assistant_msg, tool_msg) 对
        normal_history = []     # 存放其他普通消息
        
        i = 0
        while i < len(conversation_history):
            msg = conversation_history[i]
            
            # 检查是否是包含读取 SKILL.md 的 assistant 消息
            is_skill_call = False
            if msg.get('role') == 'assistant' and 'tool_calls' in msg:
                for tc in msg['tool_calls']:
                    try:
                        args = json.loads(tc['function']['arguments'])
                        if 'cat' in args.get('command', '') and 'SKILL.md' in args.get('command', ''):
                            is_skill_call = True
                            break
                    except:
                        pass
            
            if is_skill_call:
                # 这是一个发起读取 Skill 的请求，我们需要把这一轮完整的交互（请求+结果）都保下来
                assistant_msg = msg
                tool_msg = None
                
                # 向后找对应的 tool 消息
                # 注意：可能存在多个工具调用，我们需要找到对应的那个 tool 消息
                # 这里简单处理：如果下一条是 tool 消息，我们就把它作为结果
                # 更严谨的做法是匹配 tool_call_id，但在此简化场景下通常 assistant 后紧跟 tool
                j = i + 1
                while j < len(conversation_history):
                    next_msg = conversation_history[j]
                    if next_msg.get('role') == 'tool':
                        # 找到了对应的 tool 消息 (假设 SKILL.md 读取是单独的工具调用或主要调用)
                        skill_interactions.append(assistant_msg)
                        skill_interactions.append(next_msg)
                        # 将这些消息从普通流中剔除（因为它们现在被提升为 Reference Memory）
                        # 注意：i 会在循环末尾递增，所以我们要正确处理索引
                        break
                    elif next_msg.get('role') == 'user':
                        # 已经到了下一轮，说明没有找到对应的 tool 消息
                        break
                    j += 1
                
                # 即使没找到 tool 消息（异常情况），assistant 消息也不应该被当做 Skill 交互
                # 但为了安全起见，如果没有找到配对的 tool，我们就把它留在 normal_history
                if j < len(conversation_history) and conversation_history[j].get('role') == 'tool':
                    i = j + 1 # 跳过 assistant 和 tool
                    continue
            
            # 如果不是 Skill 相关，或者是落单的消息，放入普通历史
            normal_history.append(msg)
            i += 1
            
        # 2. 对普通历史进行常规压缩
        compressed_normal = self._super_compress(normal_history)
        
        # 3. 重组最终上下文
        # 顺序：[压缩摘要] -> [Skill 文档(插队)] -> [最近对话]
        
        final_history = []
        
        # 先放压缩后的摘要（如果有）
        if compressed_normal and compressed_normal[0].get('role') == 'system':
            final_history.append(compressed_normal[0]) # 摘要
            compressed_normal.pop(0) # 移除摘要，剩下的是最近对话
            
        # 插入被保护的 Skill 文档
        if skill_interactions:
            final_history.append({
                "role": "system", 
                "content": "【Reference Memory】The following are specific Skill documentations loaded previously. Always refer to them for rules and formats:"
            })
            final_history.extend(skill_interactions)
            
        # 最后放最近的普通对话
        final_history.extend(compressed_normal)
        
        return final_history

    def _super_compress(self, conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        执行常规的滑动窗口压缩（原 compress_history 逻辑）
        """
        if not conversation_history:
            return []
        
        # 提取现有的摘要消息
        existing_summaries = [msg for msg in conversation_history if msg.get('role') == 'system' and 'Earlier Conversation Summary' in msg.get('content', '')]
        
        # 识别对话轮次（每个 user 消息标志新一轮）
        rounds = self._identify_rounds(conversation_history)
        
        # 如果总轮数不超过窗口大小，不压缩
        if len(rounds) <= self.recent_window:
            return conversation_history
        
        # 计算需要压缩的轮次
        compress_round_count = len(rounds) - self.recent_window
        
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
    
    def _identify_rounds(self, conversation_history: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """
        识别对话轮次
        
        每个 user 消息标志一轮对话的开始
        一轮包括：user → assistant (可能有 tool_calls) → tool (可能多个)
        
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
            tool_name: 工具名称
            args_json: 参数 JSON 字符串
            
        Returns:
            简化的参数字符串
        """
        try:
            args = json.loads(args_json)
            
            # 针对不同工具的特殊处理
            if tool_name == 'bash':
                cmd = args.get('command', '')
                return f'"{cmd[:80]}..."' if len(cmd) > 80 else f'"{cmd}"'
            elif tool_name == 'run_python_code':
                code = args.get('code', '')
                files = args.get('input_files', [])
                code_preview = code[:50].replace('\n', ' ')
                if files:
                    return f'code="{code_preview}...", files={files}'
                return f'code="{code_preview}..."'
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
