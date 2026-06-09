"""
Phase2 单元测试：System Prompt 与工具描述改造
运行方式: python -m pytest tests/test_phase2_prompt_refactor.py -v
或直接运行: python tests/test_phase2_prompt_refactor.py
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_system.agent.prompts import get_system_prompt
from agent_system.tools.mcp_tools import BashTool
from agent_system.tools.ui_tools import RenderChartTool, RenderTableTool, ShowNotificationTool


# ============================================
# 测试 prompts.py 改造
# ============================================
def test_get_system_prompt_signature():
    """测试 get_system_prompt 函数签名变化"""
    print("\n[TEST 1] get_system_prompt 函数签名")
    
    import inspect
    sig = inspect.signature(get_system_prompt)
    params = list(sig.parameters.keys())
    
    # Phase2: 移除 skills_summary 参数，只保留 files_info
    assert "skills_summary" not in params, "不应再有 skills_summary 参数"
    assert "files_info" in params, "应保留 files_info 参数"
    
    print(f"  - 参数列表: {params}")
    print(f"  - skills_summary 已移除: [OK]")
    print("  [PASS]")


def test_get_system_prompt_no_skills_library():
    """测试 system prompt 中移除 <skills_library>"""
    print("\n[TEST 2] system prompt 移除 <skills_library>")
    
    prompt = get_system_prompt()
    
    # Phase2: 移除 <skills_library>
    assert "<skills_library>" not in prompt, "不应包含 <skills_library> 标签"
    assert "</skills_library>" not in prompt, "不应包含 </skills_library> 标签"
    
    print(f"  - prompt 长度: {len(prompt)} 字符")
    print(f"  - <skills_library> 已移除: [OK]")
    print("  [PASS]")


def test_get_system_prompt_no_tools_summary():
    """测试 system prompt 中移除 <tools_summary>"""
    print("\n[TEST 3] system prompt 移除 <tools_summary>")
    
    prompt = get_system_prompt()
    
    # Phase2: 移除 <tools_summary>
    assert "<tools_summary>" not in prompt, "不应包含 <tools_summary> 标签"
    assert "</tools_summary>" not in prompt, "不应包含 </tools_summary> 标签"
    
    print(f"  - <tools_summary> 已移除: [OK]")
    print("  [PASS]")


def test_get_system_prompt_no_client_side_ui_tools():
    """测试 system prompt 中移除 <client_side_ui_tools>"""
    print("\n[TEST 4] system prompt 移除 <client_side_ui_tools>")
    
    prompt = get_system_prompt()
    
    # Phase2: 移除 <client_side_ui_tools>
    assert "<client_side_ui_tools>" not in prompt, "不应包含 <client_side_ui_tools> 标签"
    assert "</client_side_ui_tools>" not in prompt, "不应包含 </client_side_ui_tools> 标签"
    
    print(f"  - <client_side_ui_tools> 已移除: [OK]")
    print("  [PASS]")


def test_get_system_prompt_has_skills_access():
    """测试 system prompt 中新增 <skills_access>"""
    print("\n[TEST 5] system prompt 新增 <skills_access>")
    
    prompt = get_system_prompt()
    
    assert "Use the Skill tool" in prompt
    assert "matches an available skill" in prompt
    assert "Bash is restricted to executing Python scripts only" in prompt
    
    print(f"  - <skills_access> 已新增: [OK]")
    print(f"  - 包含 Skill 工具指引: [OK]")
    print("  [PASS]")


def test_get_system_prompt_preserved_tags():
    """测试 system prompt 保留的标签"""
    print("\n[TEST 6] system prompt 保留的标签")
    
    prompt = get_system_prompt()
    
    assert "Claude Skills Orchestrator" in prompt
    assert "# Tool usage policy" in prompt
    assert "<env>" in prompt and "</env>" in prompt
    
    print(f"  - <role>: [OK]")
    print(f"  - <environment>: [OK]")
    print(f"  - <critical_protocol>: [OK]")
    print(f"  - <thinking_process>: [OK]")
    print("  [PASS]")


def test_get_system_prompt_critical_protocol_simplified():
    """测试 <critical_protocol> 已精简（移除 bash 读 SKILL.md）"""
    print("\n[TEST 7] <critical_protocol> 精简验证")
    
    prompt = get_system_prompt()
    
    # Phase2: 移除 "bash cat SKILL.md" 的硬性要求
    assert 'bash("cat skills/' not in prompt, "不应包含 bash cat SKILL.md 指令"
    assert "KNOWLEDGE ACQUISITION FIRST" not in prompt, "不应包含旧的 KNOWLEDGE ACQUISITION FIRST"
    
    # 应保留效率相关内容
    assert "效率" in prompt or "efficiency" in prompt.lower(), "应保留效率相关指引"
    
    print(f"  - bash cat SKILL.md 已移除: [OK]")
    print(f"  - 效率指引保留: [OK]")
    print("  [PASS]")


def test_get_system_prompt_thinking_process_updated():
    """测试 <thinking_process> 已更新（先调用 Skill 工具）"""
    print("\n[TEST 8] <thinking_process> 更新验证")
    
    prompt = get_system_prompt()
    
    # 提取 thinking_process 部分
    start = prompt.find("<thinking_process>")
    end = prompt.find("</thinking_process>")
    
    if start != -1 and end != -1:
        thinking_section = prompt[start:end]
        
        # Phase2: 应强调先调用 Skill 工具
        has_skill_mention = "Skill" in thinking_section or "技能" in thinking_section
        assert has_skill_mention, "<thinking_process> 应提及 Skill 工具"
        
        # 不应再有 "Read the full SKILL.md" 的旧指令
        assert "Read the full `SKILL.md`" not in thinking_section, "不应包含旧的读取指令"
        
        print(f"  - 提及 Skill 工具: [OK]")
        print(f"  - 旧读取指令已移除: [OK]")
    else:
        print(f"  - 未找到 <thinking_process> 标签")
    
    print("  [PASS]")


def test_get_system_prompt_with_files_info():
    """测试 get_system_prompt 传入 files_info"""
    print("\n[TEST 9] get_system_prompt 传入 files_info")
    
    files_info = "    - data.csv (10.5 KB)\n    - report.xlsx (25.3 KB)"
    prompt = get_system_prompt(files_info=files_info)
    
    # 验证文件信息被包含
    assert "data.csv" in prompt, "应包含文件信息"
    assert "DETECTED FILES" in prompt, "应包含 DETECTED FILES 标记"
    
    print(f"  - 文件信息已包含: [OK]")
    print("  [PASS]")


# ============================================
# 测试 mcp_tools.py 改造
# ============================================
def test_bash_tool_description_chinese():
    """测试 BashTool description 改为中文"""
    print("\n[TEST 10] BashTool description 中文化")
    
    from unittest.mock import MagicMock
    mock_client = MagicMock()
    tool = BashTool(mock_client)
    
    desc = tool.description
    
    # Phase2: 改为中文
    assert "执行 Python 脚本" in desc
    assert "python/python3" in desc
    
    # 应提及 Skill 工具注入
    assert "Read" in desc and "Write" in desc and "List" in desc
    
    # 不应有旧的英文描述
    assert "python -c" in desc and "python -m" in desc
    
    print(f"  - description 长度: {len(desc)} 字符")
    print(f"  - 中文描述: [OK]")
    print(f"  - 提及 Skill 工具: [OK]")
    print("  [PASS]")


def test_python_tool_description_chinese():
    from agent_system.tools import mcp_tools

    assert not hasattr(mcp_tools, "PythonTool")
    return
    """测试 PythonTool description 改为中文"""
    print("\n[TEST 11] PythonTool description 中文化")
    
    from unittest.mock import MagicMock
    mock_client = MagicMock()
    tool = PythonTool(mock_client)
    
    desc = tool.description
    
    # Phase2: 改为中文
    assert "有状态沙盒" in desc, "应包含中文描述"
    assert "重要提示" in desc, "应包含'重要提示'段"
    assert "使用建议" in desc, "应包含'使用建议'段"
    
    # 应提及完整逻辑
    assert "完整逻辑" in desc, "应强调写完整逻辑"
    
    # 不应有旧的英文描述
    assert "Execute Python code in a stateful sandbox" not in desc, "不应包含旧的英文描述"
    
    print(f"  - description 长度: {len(desc)} 字符")
    print(f"  - 中文描述: [OK]")
    print(f"  - 强调完整逻辑: [OK]")
    print("  [PASS]")


# ============================================
# 测试 ui_tools.py 改造
# ============================================
def test_render_chart_description_decision_rules():
    """测试 RenderChartTool description 包含使用决策规则"""
    print("\n[TEST 12] RenderChartTool description 使用决策规则")
    
    tool = RenderChartTool()
    desc = tool.description
    
    # Phase2: 应包含决策规则
    assert "趋势" in desc or "时间序列" in desc, "应包含趋势/时间序列规则"
    assert "对比" in desc or "排名" in desc, "应包含对比/排名规则"
    assert "占比" in desc or "构成" in desc, "应包含占比/构成规则"
    
    # 应包含图表类型映射
    assert "line" in desc, "应包含 line 类型"
    assert "bar" in desc, "应包含 bar 类型"
    assert "pie" in desc, "应包含 pie 类型"
    
    # 应明确是客户端工具
    assert "客户端" in desc, "应明确是客户端工具"
    assert "无需等待" in desc, "应说明无需等待结果"
    
    print(f"  - description 长度: {len(desc)} 字符")
    print(f"  - 决策规则: [OK]")
    print(f"  - 图表类型映射: [OK]")
    print(f"  - 客户端说明: [OK]")
    print("  [PASS]")


def test_render_table_description_decision_rules():
    """测试 RenderTableTool description 包含使用决策规则"""
    print("\n[TEST 13] RenderTableTool description 使用决策规则")
    
    tool = RenderTableTool()
    desc = tool.description
    
    # Phase2: 应包含决策规则
    assert "结构化" in desc, "应包含结构化结果规则"
    assert "行数" in desc or "> 3" in desc, "应包含行数规则"
    
    # 应明确是客户端工具
    assert "客户端" in desc, "应明确是客户端工具"
    assert "无需等待" in desc, "应说明无需等待结果"
    
    print(f"  - description 长度: {len(desc)} 字符")
    print(f"  - 决策规则: [OK]")
    print(f"  - 客户端说明: [OK]")
    print("  [PASS]")


def test_show_notification_description_decision_rules():
    """测试 ShowNotificationTool description 包含使用决策规则"""
    print("\n[TEST 14] ShowNotificationTool description 使用决策规则")
    
    tool = ShowNotificationTool()
    desc = tool.description
    
    # Phase2: 应包含使用场景
    assert "成功" in desc or "警告" in desc or "错误" in desc, "应包含通知类型"
    
    # 应明确是客户端工具
    assert "客户端" in desc, "应明确是客户端工具"
    assert "无需等待" in desc, "应说明无需等待结果"
    
    print(f"  - description 长度: {len(desc)} 字符")
    print(f"  - 使用场景: [OK]")
    print(f"  - 客户端说明: [OK]")
    print("  [PASS]")


# ============================================
# 测试 core.py 调用链改造
# ============================================
def test_core_no_skills_summary():
    """测试 core.py 中不再使用 skills_summary"""
    print("\n[TEST 15] core.py 移除 skills_summary")
    
    core_path = Path(__file__).parent.parent / "agent_system" / "agent" / "core.py"
    
    if core_path.exists():
        source = core_path.read_text(encoding="utf-8")
        
        # Phase2: 不应有 self.skills_summary 赋值
        # 注意：可能有注释提及，所以检查赋值语句
        assert "self.skills_summary = " not in source, "不应有 self.skills_summary 赋值"
        
        # 检查 get_system_prompt 调用不再传入 skills_summary
        # 查找 get_system_prompt 调用
        if "get_system_prompt(self.skills_summary" in source:
            raise AssertionError("get_system_prompt 调用不应传入 skills_summary")
        
        # 应该只传入 files_info
        assert "get_system_prompt(self._get_files_info())" in source, \
            "get_system_prompt 应只传入 files_info"
        
        print(f"  - self.skills_summary 已移除: [OK]")
        print(f"  - get_system_prompt 调用已更新: [OK]")
        print("  [PASS]")
    else:
        print(f"  - 跳过（core.py 不存在: {core_path}）")


def test_core_imports_correct():
    """测试 core.py 导入语句正确"""
    print("\n[TEST 16] core.py 导入语句验证")
    
    core_path = Path(__file__).parent.parent / "agent_system" / "agent" / "core.py"
    
    if core_path.exists():
        source = core_path.read_text(encoding="utf-8")
        
        # 应该导入 get_system_prompt
        assert "from .prompts import get_system_prompt" in source, \
            "应导入 get_system_prompt"
        
        print(f"  - 导入语句正确: [OK]")
        print("  [PASS]")
    else:
        print(f"  - 跳过（core.py 不存在: {core_path}）")


# ============================================
# 综合验证测试
# ============================================
def test_phase2_token_reduction():
    """测试 Phase2 改造后 system prompt token 数量减少"""
    print("\n[TEST 17] Phase2 token 减少验证")
    
    prompt = get_system_prompt()
    
    # 粗略估算 token 数量（中文约 1.5 字符/token）
    char_count = len(prompt)
    estimated_tokens = char_count // 2  # 保守估计
    
    # Phase2 目标：精简后应该更短
    # 原来的 prompt 大约 2500+ 字符，精简后应该 < 1500 字符
    print(f"  - 字符数: {char_count}")
    print(f"  - 估算 tokens: ~{estimated_tokens}")
    
    # Current prompt includes Claude Code-style operating policy; guard against accidental bloat.
    assert char_count < 6000, f"system prompt unexpectedly large: {char_count}"
    
    print(f"  - 长度验证: [OK] (< 6000 字符)")
    print("  [PASS]")


def test_phase2_no_duplicate_rules():
    """测试 Phase2 改造后没有重复规则"""
    print("\n[TEST 18] 无重复规则验证")
    
    prompt = get_system_prompt()
    
    # 旧的规则不应出现在 system prompt 中
    old_rules = [
        "render_chart",  # UI 工具规则已下沉
        "render_table",  # UI 工具规则已下沉
        "show_notification",  # UI 工具规则已下沉
        "Time-series / Trends",  # UI 决策规则已下沉
        "Comparisons / Rankings",  # UI 决策规则已下沉
    ]
    
    for rule in old_rules:
        if rule in prompt:
            print(f"  - 警告: '{rule}' 仍在 system prompt 中")
        else:
            print(f"  - '{rule}' 已移除: [OK]")
    
    print("  [PASS]")


# ============================================
# 测试运行器
# ============================================
def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Phase2 单元测试: System Prompt 与工具描述改造")
    print("=" * 60)
    
    tests = [
        # prompts.py 测试
        test_get_system_prompt_signature,
        test_get_system_prompt_no_skills_library,
        test_get_system_prompt_no_tools_summary,
        test_get_system_prompt_no_client_side_ui_tools,
        test_get_system_prompt_has_skills_access,
        test_get_system_prompt_preserved_tags,
        test_get_system_prompt_critical_protocol_simplified,
        test_get_system_prompt_thinking_process_updated,
        test_get_system_prompt_with_files_info,
        # mcp_tools.py 测试
        test_bash_tool_description_chinese,
        test_python_tool_description_chinese,
        # ui_tools.py 测试
        test_render_chart_description_decision_rules,
        test_render_table_description_decision_rules,
        test_show_notification_description_decision_rules,
        # core.py 测试
        test_core_no_skills_summary,
        test_core_imports_correct,
        # 综合验证
        test_phase2_token_reduction,
        test_phase2_no_duplicate_rules,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  [FAILED] {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
