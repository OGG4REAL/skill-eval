"""
Agent 核心
实现主对话循环和工具调用逻辑
"""
import json
import time
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from .llm_client import LLMClient
from .prompts import get_system_prompt, format_tool_result
from .memory import MemoryManager
from ..tools.base import ToolRegistry, ClientSideToolResult
from ..skills.manager import SkillManager
from ..config import Config
from ..evaluation.recorder import RunRecorder
from ..evaluation.scorer import RuleScorer
from ..evaluation.registry import RunsRegistry

# 从 Config 类获取常量
PERSISTED_OUTPUT_THRESHOLD = Config.PERSISTED_OUTPUT_THRESHOLD
PERSISTED_OUTPUT_PREVIEW_SIZE = Config.PERSISTED_OUTPUT_PREVIEW_SIZE
TOOL_RESULTS_DIR_NAME = Config.TOOL_RESULTS_DIR_NAME


def _repair_xml_garbled_args(tool_args: dict) -> dict:
    """
    Repair tool args where GLM's Anthropic-compatible API mixes XML tags into JSON keys.
    Pattern: {"key1</arg_key>value1</arg_value><arg_key>key2": actual_value2, ...}
    → {"key1": "value1", "key2": actual_value2, ...}
    """
    repaired = {}
    for key, value in tool_args.items():
        if "</arg_key>" in key:
            parts = key.split("</arg_key>", 1)
            first_key = parts[0]
            remainder = parts[1]
            if "</arg_value><arg_key>" in remainder:
                val_part, second_key = remainder.split("</arg_value><arg_key>", 1)
                repaired[first_key] = val_part
                repaired[second_key] = value
            else:
                repaired[first_key] = value
        else:
            repaired[key] = value
    return repaired


# 回调类型定义
LogCallback = Callable[[str, str], None]  # (event_type, message)


console = Console()


class Agent:
    """智能 Agent：负责对话循环和工具调用"""
    
    def __init__(self, skill_manager: SkillManager, tool_registry: ToolRegistry, 
                 log_file: str = "chat_history.log", uploads_dir: str = None,
                 variant_context: Optional[Dict[str, Any]] = None,
                 sessions_root: Optional[Path] = None):
        """
        初始化 Agent
        
        Args:
            skill_manager: 技能管理器
            tool_registry: 工具注册表
            log_file: 聊天记录保存路径
            uploads_dir: 用户上传文件目录
            variant_context: 可选的 variant 实验条件（VariantManager.resolve_variant() 输出）。
                             传入后会写入每次 run 的 RunRecord metadata。
            sessions_root: 可选的会话根目录。None 使用 Config.SESSIONS_ROOT。
        """
        self.skill_manager = skill_manager
        self.tool_registry = tool_registry
        self.llm_client = LLMClient()
        self.conversation_history: List[Dict[str, Any]] = []
        self.uploads_dir = Path(uploads_dir) if uploads_dir else None
        self.variant_context: Optional[Dict[str, Any]] = variant_context
        self.sessions_root: Path = Path(sessions_root) if sessions_root else Config.SESSIONS_ROOT
        
        # 初始化结构化历史记录文件 (与日志文件同目录)
        self.log_file = Path(log_file)
        self.history_file = self.log_file.parent / "history.json"
        
        # 初始化记忆管理器（保留最近3轮完整对话轮次）
        # 注：recent_window 参数已废弃，实际使用 recent_conversation_rounds
        self.memory_manager = MemoryManager(recent_conversation_rounds=3)
        
        # 初始化对话历史（从文件加载或新建）
        self.conversation_history: List[Dict[str, Any]] = []
        self._load_history()
        
        # 初始化系统提示词（Phase2: 技能清单已移至 Skill 工具 description）
        self.system_prompt = get_system_prompt(self._get_files_info())
        
        # 初始化日志文件
        self._init_log_file()

        console.print(Panel(
            "[green]Agent 初始化完成[/green]\n\n" + 
            f"可用技能：{len(skill_manager.list_skills())} 个\n" +
            f"可用工具：{len(tool_registry.tools)} 个\n" +
            f"聊天记录: {self.log_file.absolute()}",
            title="Claude Skills Agent"
        ))
    
    def _get_files_info(self) -> str:
        """扫描上传目录，生成文件摘要"""
        if not self.uploads_dir or not self.uploads_dir.exists():
            return ""
        
        try:
            files = list(self.uploads_dir.glob("*"))
            if not files:
                return ""
                
            lines = []
            for f in files:
                if f.is_file():
                    size_kb = f.stat().st_size / 1024
                    lines.append(f"    - {f.name} ({size_kb:.1f} KB)")
            return "\n".join(lines)
        except Exception as e:
            console.print(f"[yellow]警告：扫描上传目录失败: {e}[/yellow]")
            return ""

    def _persist_tool_output(self, result_str: str, tool_call_id: str, tool_name: str) -> str:
        """
        L1 门卫：检查工具输出大小，超过阈值则持久化到文件

        参考 Claude Code 的 persisted-output 机制：
        - 工具结果超过 8KB 时，完整输出存入磁盘
        - 只将 ~2KB 预览（包裹在 <persisted-output> 标签中）写入 LLM 上下文
        - LLM 如需更多细节，可通过 Read 工具读取持久化文件

        Args:
            result_str: 工具返回的原始字符串
            tool_call_id: 工具调用 ID
            tool_name: 工具名称

        Returns:
            如果超过阈值，返回预览格式字符串；否则返回原始 result_str
        """
        if len(result_str) <= PERSISTED_OUTPUT_THRESHOLD:
            return result_str

        # 确保 .tool-results 目录存在
        tool_results_dir = self.log_file.parent / TOOL_RESULTS_DIR_NAME
        tool_results_dir.mkdir(parents=True, exist_ok=True)

        # 写入完整输出到文件
        output_file = tool_results_dir / f"{tool_call_id}.txt"
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(result_str)

            # 生成预览格式
            size_kb = len(result_str) / 1024
            preview = result_str[:PERSISTED_OUTPUT_PREVIEW_SIZE]

            preview_str = f"""<persisted-output>
Output too large ({size_kb:.1f}KB). Full output saved to:
{TOOL_RESULTS_DIR_NAME}/{tool_call_id}.txt

Preview (first {PERSISTED_OUTPUT_PREVIEW_SIZE} chars):
{preview}
... [truncated]
</persisted-output>"""

            console.print(f"  [yellow]工具输出已持久化 ({size_kb:.1f}KB -> {TOOL_RESULTS_DIR_NAME}/{tool_call_id}.txt)[/yellow]")
            return preview_str

        except Exception as e:
            console.print(f"  [red]持久化失败: {e}，返回原始输出[/red]")
            return result_str

    def _snapshot_tracked_artifacts(self) -> set[Path]:
        base_dir = self.log_file.parent
        tracked_dirs = [
            base_dir / "temp",
            base_dir / "output",
            base_dir / TOOL_RESULTS_DIR_NAME,
        ]
        files: set[Path] = set()
        for root in tracked_dirs:
            if not root.exists():
                continue
            try:
                files.update(path for path in root.rglob("*") if path.is_file())
            except OSError:
                continue
        return files

    def _record_new_tracked_artifacts(self, recorder: RunRecorder, before: set[Path]) -> None:
        base_dir = self.log_file.parent
        for path in sorted(self._snapshot_tracked_artifacts() - before):
            try:
                rel_path = path.relative_to(base_dir).as_posix()
            except ValueError:
                continue
            recorder.record_artifact_created(rel_path)

    def _init_log_file(self):
        """初始化日志文件"""
        if not self.log_file.exists():
            with open(self.log_file, 'w', encoding='utf-8') as f:
                f.write(f"=== Claude Skills Agent 聊天记录 ===\n")
                f.write(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("="*80 + "\n\n")

    def _load_history(self):
        """从 JSON 文件加载对话历史"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.conversation_history = json.load(f)
                console.print(f"[dim]已加载历史会话 ({len(self.conversation_history)} 条消息)[/dim]")
            except Exception as e:
                console.print(f"[yellow]警告：加载历史记录失败: {e}[/yellow]")
                self.conversation_history = []
        else:
            self.conversation_history = []

    def _save_history(self):
        """保存对话历史到 JSON 文件"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.conversation_history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            console.print(f"[yellow]警告：保存历史记录失败: {e}[/yellow]")
    
    def _log_interaction(self, user_input: str, agent_response: str, iteration: int, execution_log: List[str] = None):
        """记录一次交互到日志文件"""
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"\n{'='*80}\n")
                f.write(f"时间: {timestamp}\n")
                f.write(f"{'='*80}\n\n")
                f.write(f"用户输入:\n{user_input}\n\n")
                
                # 如果有执行日志，记录完整的执行过程
                if execution_log:
                    f.write(f"执行过程 (共 {iteration} 轮):\n")
                    f.write("-" * 80 + "\n")
                    for log_entry in execution_log:
                        f.write(log_entry + "\n")
                    f.write("-" * 80 + "\n\n")
                
                f.write(f"Agent 最终回复:\n{agent_response}\n\n")
        except Exception as e:
            console.print(f"[yellow]警告：保存日志失败: {e}[/yellow]")

    def _inject_skill_context(
        self,
        skill_name: str,
        recorder: RunRecorder,
        execution_log: List[str],
        emit: Optional[LogCallback] = None,
        args: str = "",
    ) -> None:
        """
        复用日常 Skill 注入范式，将 Skill 内容注入到对话历史。

        这里不走 LLM 触发的 Skill tool_call 计数，因为 benchmark 预注入场景
        关注的是“已加载 Skill 后开始任务”的效果，而不是 routing/选择成本。
        """
        skill_tool = self.tool_registry.get("Skill")
        if not skill_tool or not getattr(skill_tool, "skill_injector", False):
            raise RuntimeError("Skill 工具未注册，无法执行技能注入")

        result_str = skill_tool.execute(skill=skill_name, args=args)
        if result_str.startswith("Error:"):
            raise RuntimeError(result_str)

        injection_content = skill_tool.get_injection_content()
        self.conversation_history.append({
            "role": "assistant",
            "content": ""
        })
        self.conversation_history.append({
            "role": "user",
            "content": injection_content
        })

        recorder.record_skill_injected(skill_name)
        console.print(f"[cyan]预注入技能 {skill_name} 到上下文[/cyan]")
        execution_log.append(f"预注入技能: {skill_name}")
        if emit:
            emit("skill_inject", f"技能 {skill_name} 已预注入")

    def _apply_variant_pre_injections(
        self,
        recorder: RunRecorder,
        execution_log: List[str],
        emit: Optional[LogCallback] = None,
    ) -> None:
        """根据 variant_context 在正式处理用户问题前预注入技能。"""
        if not self.variant_context:
            return

        skill_names = list(self.variant_context.get("pre_injected_skills", []))
        if not skill_names:
            return

        for skill_name in skill_names:
            self._inject_skill_context(
                skill_name=skill_name,
                recorder=recorder,
                execution_log=execution_log,
                emit=emit,
            )
        self._save_history()
    
    def run(self, user_input: str, max_iterations: int = None, 
            callback: LogCallback = None) -> Dict[str, Any]:
        """
        运行 Agent，处理用户输入
        
        Args:
            user_input: 用户输入
            max_iterations: 最大迭代次数（工具调用轮数）
            callback: 实时日志回调函数，签名为 (event_type, message)
                      event_type 可以是: "thinking", "tool_call", "tool_result", 
                                        "client_side_tool", "complete", "error"
            
        Returns:
            包含以下字段的字典:
            - response: Agent 的最终回复文本
            - client_side_tools: 客户端工具调用列表 (如果有)
            - iterations: 实际迭代次数
            - run_id: 本次运行 ID
        """
        max_iterations = max_iterations or Config.MAX_ITERATIONS
        
        # 初始化 RunRecorder
        recorder = self._init_recorder(user_input)
        
        # 客户端工具调用收集器
        client_side_tool_calls: List[ClientSideToolResult] = []
        
        def _emit(event_type: str, message: str):
            """内部辅助：触发回调"""
            if callback:
                try:
                    callback(event_type, message)
                except Exception as e:
                    console.print(f"[yellow]回调执行失败: {e}[/yellow]")
        
        # 实时更新文件信息到系统提示词
        self.system_prompt = get_system_prompt(self._get_files_info())
        
        # 压缩旧的对话历史（保留最近3轮完整，压缩更早的）
        self.conversation_history = self.memory_manager.compress_history(
            self.conversation_history
        )

        # 记录完整执行过程
        execution_log = []

        # benchmark 预注入：复用日常 Skill 注入内容格式，再开始处理用户问题
        self._apply_variant_pre_injections(
            recorder=recorder,
            execution_log=execution_log,
            emit=_emit,
        )
        
        # 添加用户消息到历史
        self.conversation_history.append({
            "role": "user",
            "content": user_input
        })
        self._save_history()  # 立即保存用户输入
        
        iteration = 0
        run_status = "passed"
        
        try:
            while iteration < max_iterations:
                iteration += 1
                
                console.print(f"\n[cyan]-> 第 {iteration} 轮思考...[/cyan]")
                execution_log.append(f"\n-> 第 {iteration} 轮思考...")
                _emit("thinking", f"第 {iteration} 轮思考...")
                recorder.record_iteration_start(iteration)
                
                # 构建消息列表（系统提示词 + 对话历史）
                messages = [
                    {"role": "system", "content": self.system_prompt}
                ] + self.conversation_history
                
                # 获取工具定义
                tools = self.tool_registry.get_all_definitions()
                
                # 调用 LLM
                llm_start = recorder.record_llm_call_start()
                try:
                    response = self.llm_client.chat(messages, tools=tools)
                    meta = response.get("_meta", {})
                    recorder.record_llm_call_finish(
                        llm_start,
                        model=meta.get("model"),
                        provider=meta.get("provider"),
                        usage=meta.get("usage"),
                    )
                except Exception as e:
                    recorder.record_llm_call_finish(llm_start)
                    error_msg = f"LLM 调用失败：{e}"
                    console.print(f"[red]{error_msg}[/red]")
                    execution_log.append(error_msg)
                    _emit("error", error_msg)
                    run_status = "failed"
                    return self._finalize_run(
                        recorder, run_status, iteration,
                        error_msg, [], client_side_tool_calls,
                        user_input, execution_log
                    )
                
                # 处理响应
                assistant_message = {
                    "role": "assistant",
                    "content": response.get("content")
                }
                
                # 记录 LLM 的思考内容（如果有）
                llm_content = response.get("content")
                if llm_content:
                    console.print(f"[dim]LLM 思考: {llm_content[:200]}{'...' if len(llm_content) > 200 else ''}[/dim]")
                    execution_log.append("LLM 思考内容:")
                    execution_log.append(f"{llm_content}")
                    execution_log.append("")
                    _emit("thinking", llm_content)
                    recorder.record_thinking(llm_content)
                
                # 检查是否有工具调用
                tool_calls = response.get("tool_calls", [])
                
                if not tool_calls:
                    final_response = response.get("content") or "完成。"
                    
                    self.conversation_history.append(assistant_message)
                    self._save_history()
                    
                    execution_log.append("Agent 完成任务（无需调用工具）")
                    self._log_interaction(user_input, final_response, iteration, execution_log)
                    
                    console.print("\n[green]Agent 完成任务[/green]")
                    recorder.mark_final_response()
                    _emit("complete", final_response)
                    
                    return self._finalize_run(
                        recorder, "passed", iteration,
                        final_response, [], client_side_tool_calls,
                        user_input, execution_log
                    )
                
                # 有工具调用，需要执行工具
                console.print(f"[yellow]需要调用 {len(tool_calls)} 个工具[/yellow]")
                execution_log.append(f"需要调用 {len(tool_calls)} 个工具")
                _emit("tool_call", f"需要调用 {len(tool_calls)} 个工具")
                
                assistant_message["tool_calls"] = tool_calls
                self.conversation_history.append(assistant_message)
                self._save_history()
                
                for tool_call in tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool_args_str = tool_call["function"]["arguments"]
                    
                    try:
                        tool_args = json.loads(tool_args_str)
                    except json.JSONDecodeError:
                        tool_args = {}

                    # GLM 模型有时会将 XML 标签混入 JSON key，修复它
                    if any("</arg_key>" in str(k) for k in tool_args):
                        tool_args = _repair_xml_garbled_args(tool_args)
                    
                    console.print(f"  -> 调用工具: [bold]{tool_name}[/bold]")
                    console.print(f"    参数: {tool_args}")
                    
                    execution_log.append(f"  -> 调用工具: {tool_name}")
                    execution_log.append(f"    参数: {json.dumps(tool_args, ensure_ascii=False, indent=6)}")
                    _emit("tool_call", f"调用工具: {tool_name}")
                    
                    tool = self.tool_registry.get(tool_name)
                    
                    # ============================================
                    # Skill 注入工具
                    # ============================================
                    if tool and getattr(tool, 'skill_injector', False):
                        tc_start = recorder.record_tool_call_start(tool_name, tool_args)
                        result_str = tool.execute(**tool_args)
                        
                        console.print(f"  [cyan]{result_str}[/cyan]")
                        execution_log.append(f"  {result_str}")
                        
                        if result_str.startswith("Error:"):
                            recorder.record_tool_call_finish(tool_name, tc_start, status="error", error=result_str)
                            self.conversation_history.append({
                                "role": "tool",
                                "tool_call_id": tool_call["id"],
                                "name": tool_name,
                                "content": result_str
                            })
                            self._save_history()
                            _emit("error", result_str)
                            continue
                        
                        recorder.record_tool_call_finish(tool_name, tc_start, status="success")
                        
                        self.conversation_history.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "name": tool_name,
                            "content": result_str
                        })
                        self.conversation_history.append({
                            "role": "assistant",
                            "content": ""
                        })
                        
                        injection_content = tool.get_injection_content()
                        self.conversation_history.append({
                            "role": "user",
                            "content": injection_content
                        })
                        
                        injected_skill = tool._pending_skill
                        recorder.record_skill_injected(injected_skill)
                        _emit("skill_inject", f"技能 {injected_skill} 已注入")
                        execution_log.append(f"  技能注入: {injected_skill}")
                        console.print(f"  [cyan]技能 {injected_skill} 已注入到上下文[/cyan]")
                        
                        self._save_history()
                        continue
                    
                    # ============================================
                    # 客户端工具
                    # ============================================
                    elif tool and getattr(tool, 'client_side', False):
                        console.print(f"  [magenta]客户端工具，跳过后端执行[/magenta]")
                        execution_log.append(f"  客户端工具，跳过后端执行")
                        
                        client_result = ClientSideToolResult(
                            tool_name=tool_name,
                            arguments=tool_args,
                            description=f"前端将渲染 {tool_name}"
                        )
                        client_side_tool_calls.append(client_result)
                        result_str = client_result.to_message()
                        
                        recorder.record_client_tool(tool_name, tool_args)
                        
                        _emit("client_side_tool", json.dumps({
                            "name": tool_name,
                            "arguments": tool_args
                        }, ensure_ascii=False))
                        
                        execution_log.append(f"  客户端工具结果: {result_str}")
                    
                    # ============================================
                    # 普通工具
                    # ============================================
                    else:
                        tc_start = recorder.record_tool_call_start(tool_name, tool_args)
                        artifact_snapshot = self._snapshot_tracked_artifacts()
                        try:
                            result = self.tool_registry.execute(tool_name, **tool_args)
                            result_str = str(result)
                            recorder.record_tool_call_finish(
                                tool_name, tc_start, status="success",
                                output=result_str if tool_name == "Bash" else None,
                            )

                            # 检测产物创建
                            if tool_name == "Write" and "path" in tool_args:
                                recorder.record_artifact_created(tool_args["path"])
                            
                            console.print(f"  工具执行成功（返回 {len(result_str)} 字符）")
                            if result_str.strip():
                                console.print("  工具输出:", style="dim")
                                if len(result_str) > 2000:
                                    console.print(result_str[:2000] + f"\n... [省略 {len(result_str)-2000} 字符]", markup=False, soft_wrap=True)
                                else:
                                    console.print(result_str, markup=False, soft_wrap=True)
                            
                            if len(result_str) > 2000:
                                log_result = result_str[:1000] + f"\n\n... [中间省略 {len(result_str)-2000} 字符] ...\n\n" + result_str[-1000:]
                            else:
                                log_result = result_str
                            
                            execution_log.append(f"  工具执行成功（返回 {len(result_str)} 字符）")
                            execution_log.append(f"    结果:\n{log_result}")
                            _emit("tool_result", f"工具 {tool_name} 执行成功")
                            
                        except Exception as e:
                            result_str = f"工具执行失败：{str(e)}"
                            recorder.record_tool_call_finish(tool_name, tc_start, status="error", error=str(e))
                            console.print(f"  [red]{result_str}[/red]")
                            execution_log.append(f"  {result_str}")
                            _emit("error", result_str)

                        self._record_new_tracked_artifacts(recorder, artifact_snapshot)

                    # L1 门卫：检查并持久化大输出
                    persisted = self._persist_tool_output(result_str, tool_call["id"], tool_name)
                    if persisted != result_str:
                        recorder.record_artifact_created(f"{TOOL_RESULTS_DIR_NAME}/{tool_call['id']}.txt")
                    result_str = persisted

                    self.conversation_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": tool_name,
                        "content": result_str
                    })
                    self._save_history()
            
            # 达到最大迭代次数
            warning_msg = f"已达到最大迭代次数（{max_iterations}），任务可能未完成。"
            console.print(f"[yellow]{warning_msg}[/yellow]")
            execution_log.append(warning_msg)
            _emit("error", warning_msg)
            self._log_interaction(user_input, warning_msg, max_iterations, execution_log)
            
            return self._finalize_run(
                recorder, "failed", max_iterations,
                warning_msg, [], client_side_tool_calls,
                user_input, execution_log
            )
        
        except Exception as e:
            error_msg = f"Agent 运行异常：{str(e)}"
            console.print(f"[red]{error_msg}[/red]")
            return self._finalize_run(
                recorder, "failed", iteration,
                error_msg, [], client_side_tool_calls,
                user_input, execution_log
            )

    def _init_recorder(self, user_input: str) -> RunRecorder:
        """初始化本次 run 的 Recorder"""
        session_id = self.log_file.parent.name
        recorder = RunRecorder(
            session_id=session_id,
            sessions_root=self.sessions_root,
            user_input=user_input,
        )
        # 尝试匹配 task_id
        evaluations_dir = Config.WORKSPACE_ROOT / "evaluations"
        try:
            registry = RunsRegistry(evaluations_dir)
            recorder.run_record.task_id = registry.match_task_id(user_input)
        except Exception:
            pass

        if self.variant_context:
            vc = self.variant_context
            recorder.run_record.variant_id = vc.get("variant_id", "baseline")
            recorder.run_record.enabled_skills = list(vc.get("enabled_skills", []))
            recorder.run_record.skill_version_map = dict(vc.get("skill_version_map", {}))
            recorder.run_record.routing_enabled = vc.get("routing_enabled")

        return recorder

    def _finalize_run(
        self,
        recorder: RunRecorder,
        status: str,
        iterations: int,
        response: str,
        execution_log_extra: List[str],
        client_side_tool_calls: List[ClientSideToolResult],
        user_input: str,
        execution_log: List[str],
    ) -> Dict[str, Any]:
        """结束 run，执行评分、落盘、更新索引"""
        try:
            # 先把 recorder 内部累计的统计量同步到 run_record，
            # 确保 scorer 读到的数据是完整的。
            recorder.run_record.iterations = iterations
            recorder.run_record.status = status
            recorder.run_record.tool_calls = recorder.tool_calls_count
            recorder.run_record.tool_errors = recorder.tool_errors_count
            recorder.run_record.skills = list(recorder._injected_skills)
            recorder.run_record.duration_ms = int(
                (time.time() - recorder._start_time) * 1000
            )

            scorer = RuleScorer()
            eval_record = scorer.score(recorder.run_record, recorder.artifacts_list)
            run_record = recorder.finalize(status=status, iterations=iterations, eval_record=eval_record)
            
            evaluations_dir = Config.WORKSPACE_ROOT / "evaluations"
            registry = RunsRegistry(evaluations_dir)
            registry.append_run(run_record, eval_record)
        except Exception as e:
            console.print(f"[yellow]评估落盘失败（不影响主流程）: {e}[/yellow]")
            try:
                recorder.finalize(status=status, iterations=iterations)
            except Exception:
                pass

        return {
            "response": response,
            "client_side_tools": [
                {
                    "tool_name": cst.tool_name,
                    "arguments": cst.arguments,
                    "description": cst.description
                }
                for cst in client_side_tool_calls
            ],
            "iterations": iterations,
            "run_id": recorder.run_id,
        }
    
    def reset_conversation(self):
        """重置对话历史"""
        self.conversation_history.clear()
        if self.history_file.exists():
            try:
                self.history_file.unlink()
                console.print("[dim]历史记录文件已删除[/dim]")
            except Exception as e:
                console.print(f"[yellow]警告：删除历史记录文件失败: {e}[/yellow]")
        console.print("[dim]对话历史已清空[/dim]")
    
    def get_conversation_summary(self) -> str:
        """获取对话摘要"""
        if not self.conversation_history:
            return "暂无对话历史"
        
        summary_lines = []
        for msg in self.conversation_history:
            role = msg["role"]
            content = msg.get("content", "")
            
            if role == "user":
                summary_lines.append(f"用户: {content[:100]}...")
            elif role == "assistant":
                if content:
                    summary_lines.append(f"助手: {content[:100]}...")
                if "tool_calls" in msg:
                    tools = [tc["function"]["name"] for tc in msg["tool_calls"]]
                    summary_lines.append(f"   调用工具: {', '.join(tools)}")
            elif role == "tool":
                tool_name = msg.get("name", "unknown")
                summary_lines.append(f"   {tool_name} 返回结果")
        
        return "\n".join(summary_lines)

