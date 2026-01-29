"""
主入口和 CLI
重构后：使用 Docker MCP 沙箱架构
"""
import sys
import argparse
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from .config import Config
from .skills.manager import SkillManager
from .tools.base import ToolRegistry
from .tools.mcp_tools import MCPClient, BashTool, PythonTool
from .tools.skill_tool import SkillTool
from .tools.ui_tools import register_ui_tools
from .agent.core import Agent
from .session import derive_session_id, ensure_session_dirs


# Rich console 配置（Windows 兼容）
if sys.platform == "win32":
    console = Console(legacy_windows=False)
else:
    console = Console()


def setup_system(log_file: str = "chat_history.log", session_id: str | None = None):
    """
    初始化 Agent 系统
    
    架构：
    1. SkillManager 负责提供元数据（给 system prompt / Skill 工具）
    2. Skill 工具负责注入 SKILL.md（以 user 消息注入）
    3. Agent 通过 run_python_code 工具（MCP）执行代码
    4. 所有工具在 Docker 容器内执行，共享有状态的 Python 环境
    
    Args:
        log_file: 聊天记录保存路径
        session_id: 可选的会话 ID
    
    Returns:
        Agent 实例
    """
    console.print("\n[bold cyan]初始化 Claude Skills Agent (Docker MCP 架构)[/bold cyan]\n")
    
    # 1. 验证配置
    try:
        Config.validate()
        console.print("[green]✓ 配置验证通过[/green]")
    except ValueError as e:
        console.print(f"[red]配置错误：{e}[/red]")
        console.print("\n请创建 .env 文件并设置以下环境变量：")
        console.print("  - DEEPSEEK_API_KEY")
        console.print(f"\n参考 env.example 文件")
        sys.exit(1)
    
    # 2. 初始化会话目录
    derived_session_id = derive_session_id(log_file, session_id)
    session_base, session_uploads, session_output, session_log = ensure_session_dirs(derived_session_id)
    
    console.print(f"[dim]会话 ID: {derived_session_id}[/dim]")
    console.print(f"[dim]工作目录: {session_base}[/dim]")
    
    # 如果是默认日志文件且不是绝对路径，将其放入会话目录
    log_path = Path(log_file)
    if log_path.name == "chat_history.log" and (not log_path.is_absolute()):
        log_file = str(session_log)

    # 3. 初始化技能管理器（只加载元数据）
    console.print(f"\n[cyan]扫描技能目录:[/cyan] {Config.SKILLS_DIR}")
    skill_manager = SkillManager(Config.SKILLS_DIR)
    
    available_skills = skill_manager.list_skills()
    if available_skills:
        console.print(f"[green]✓ 发现 {len(available_skills)} 个技能:[/green] {', '.join(available_skills)}")
    else:
        console.print("[yellow]⚠ 未找到任何技能（SKILL.md 文件）[/yellow]")
    
    # 4. 初始化 MCP 客户端（所有工具共享）
    console.print(f"\n[cyan]初始化 Docker MCP 沙箱...[/cyan]")
    console.print(f"[dim]镜像: {Config.SANDBOX_IMAGE}[/dim]")
    
    mcp_client = MCPClient(
        session_id=derived_session_id,
        workspace_path=session_base,
        skills_path=Config.SKILLS_DIR,
    )
    
    # 5. 注册工具
    console.print("\n[cyan]注册核心工具:[/cyan]")
    tool_registry = ToolRegistry()
    
    # Bash 工具
    bash_tool = BashTool(mcp_client)
    tool_registry.register(bash_tool)
    console.print(f"  [green]✓[/green] {bash_tool.name:20s} - 文件探索（容器内执行）")
    
    # Python 工具
    python_tool = PythonTool(mcp_client, output_dir=session_output)
    tool_registry.register(python_tool)
    console.print(f"  [green]✓[/green] {python_tool.name:20s} - Python 执行（有状态 REPL）")
    
    # Skill 工具（技能加载与注入）
    skill_tool = SkillTool(skill_manager)
    tool_registry.register(skill_tool)
    console.print(f"  [green]✓[/green] {skill_tool.name:20s} - 技能加载与注入")
    
    # UI 工具（客户端执行）
    console.print("\n[cyan]注册 UI 工具（客户端执行）:[/cyan]")
    register_ui_tools(tool_registry)
    ui_tool_count = sum(1 for t in tool_registry.tools.values() if getattr(t, 'client_side', False))
    console.print(f"  [green]✓[/green] 已注册 {ui_tool_count} 个客户端工具")
    
    console.print(f"\n[green]✓ 已注册 {len(tool_registry.tools)} 个工具[/green]")
    
    # 6. 初始化 Agent
    agent = Agent(
        skill_manager=skill_manager,
        tool_registry=tool_registry,
        log_file=log_file,
        uploads_dir=session_uploads
    )
    
    # 保存 MCP 客户端引用以便清理
    agent._mcp_client = mcp_client
    
    console.print("[green]✓ Agent 初始化完成[/green]\n")
    
    return agent


def display_welcome():
    """显示欢迎信息"""
    welcome_text = """
# Claude Skills Agent

**架构**: Docker MCP Sandbox (有状态执行)

**核心特性**:
- 通过 bash 自由探索文件系统
- Skill 工具注入技能文档（减少轮次）
- 有状态的 Python 执行环境（变量跨调用保留）
- 本地 Docker 沙箱（无需云服务）

**使用方式**:
1. 直接提问，Agent 会自动选择合适的技能
2. Agent 会主动读取文档和代码来学习
3. 查看日志文件了解详细的思考过程
"""
    console.print(Panel(welcome_text, border_style="cyan"))


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Claude Skills Agent with Docker MCP Sandbox",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("query", nargs="?", help="用户查询（可选，不提供则进入交互模式）")
    parser.add_argument("--log", default="chat_history.log", help="日志文件路径（默认: chat_history.log）")
    parser.add_argument("--max-iterations", type=int, default=Config.MAX_ITERATIONS, 
                       help=f"最大迭代次数（默认: {Config.MAX_ITERATIONS}）")
    parser.add_argument("--no-welcome", action="store_true", help="不显示欢迎信息")
    parser.add_argument("--session-id", help="显式指定会话 ID（覆盖日志文件推导）")
    
    args = parser.parse_args()
    
    # 显示欢迎信息
    if not args.no_welcome:
        display_welcome()
    
    # 初始化系统
    agent = setup_system(log_file=args.log, session_id=args.session_id)
    
    try:
        if args.query:
            # 单次查询模式
            console.print(f"[bold cyan]用户查询:[/bold cyan] {args.query}\n")
            console.print("[dim]详细执行过程请查看日志文件[/dim]\n")
            console.print("=" * 80)
            
            result = agent.run(args.query, max_iterations=args.max_iterations)
            
            console.print("=" * 80)
            console.print(f"\n[bold green]Agent 回复:[/bold green]\n{result['response']}\n")
            
            # 显示客户端工具调用信息（如果有）
            if result.get('client_side_tools'):
                console.print(f"[magenta]前端渲染任务: {len(result['client_side_tools'])} 个[/magenta]")
                for tool_info in result['client_side_tools']:
                    console.print(f"  - {tool_info['tool_name']}")
            
            console.print(f"[dim]完整日志已保存到: {args.log}[/dim]")
        else:
            # 交互模式
            console.print("[cyan]进入交互模式[/cyan]")
            console.print("[dim]输入 'exit' 或 'quit' 退出，输入 'help' 查看帮助[/dim]\n")
            
            while True:
                try:
                    user_input = console.input("\n[bold cyan]你:[/bold cyan] ").strip()
                    
                    if not user_input:
                        continue
                    
                    # 处理特殊命令
                    if user_input.lower() in ['exit', 'quit', 'q']:
                        console.print("\n[yellow]再见！[/yellow]")
                        break
                    
                    if user_input.lower() == 'help':
                        console.print("""
[cyan]可用命令:[/cyan]
  - 直接输入问题，Agent 会自动处理
  - exit/quit/q: 退出程序
  - help: 显示此帮助信息
  
[cyan]示例问题:[/cyan]
  - 分析 data.csv 文件
  - 总结这个 CSV 数据
  - 对数据进行可视化分析
""")
                        continue
                    
                    # 执行查询
                    console.print("\n[dim]详细执行过程请查看日志文件[/dim]\n")
                    console.print("=" * 80)
                    
                    result = agent.run(user_input, max_iterations=args.max_iterations)
                    
                    console.print("=" * 80)
                    console.print(f"\n[bold green]Agent:[/bold green]\n{result['response']}")
                    
                    # 显示客户端工具调用信息（如果有）
                    if result.get('client_side_tools'):
                        console.print(f"\n[magenta]前端渲染任务: {len(result['client_side_tools'])} 个[/magenta]")
                        for tool_info in result['client_side_tools']:
                            console.print(f"  - {tool_info['tool_name']}")
                    
                except KeyboardInterrupt:
                    console.print("\n\n[yellow]再见！[/yellow]")
                    break
                except Exception as e:
                    console.print(f"\n[red]错误: {str(e)}[/red]")
                    console.print("[dim]详细错误信息请查看日志文件[/dim]")
    
    finally:
        # 清理资源
        console.print("\n[dim]正在清理资源...[/dim]")
        
        # 清理 MCP 客户端（停止容器）
        if hasattr(agent, '_mcp_client') and agent._mcp_client:
            try:
                agent._mcp_client.cleanup()
            except Exception as e:
                console.print(f"[dim]清理 MCP 客户端失败: {e}[/dim]")
        
        # 清理其他工具
        for tool_name, tool in agent.tool_registry.tools.items():
            if hasattr(tool, 'cleanup'):
                try:
                    tool.cleanup()
                except Exception as e:
                    console.print(f"[dim]清理 {tool_name} 失败: {e}[/dim]")
        
        console.print("[dim]资源清理完成[/dim]")


if __name__ == "__main__":
    main()
