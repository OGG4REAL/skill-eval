"""
Skill 工具单元测试：Phase1 Skill 工具引入与适配
运行方式: python -m pytest tests/test_skill_tool.py -v
或直接运行: python tests/test_skill_tool.py
"""
import json
import sys
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

# 修复 Windows 控制台编码问题
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_system.tools.base import BaseTool, ToolRegistry
from agent_system.tools.skill_tool import SkillTool, SKILL_TOOL_DESCRIPTION_TEMPLATE
from agent_system.skills.manager import SkillManager


# ============================================
# 测试辅助：Mock SkillManager
# ============================================
def create_mock_skill_manager():
    """创建一个 Mock 的 SkillManager"""
    mock_manager = MagicMock(spec=SkillManager)
    
    # 模拟技能数据
    mock_manager.skills = {
        "csv-data-summarizer": {
            "metadata": {"name": "csv-data-summarizer", "description": "CSV 数据分析与可视化"},
            "file_path": Path("/workspace/skills/csv-data-summarizer/SKILL.md"),
            "dir_path": Path("/workspace/skills/csv-data-summarizer")
        },
        "fin-advisor-math": {
            "metadata": {"name": "fin-advisor-math", "description": "投顾场景的数学计算"},
            "file_path": Path("/workspace/skills/fin-advisor-math/SKILL.md"),
            "dir_path": Path("/workspace/skills/fin-advisor-math")
        }
    }
    
    # 模拟方法
    mock_manager.list_skills.return_value = ["csv-data-summarizer", "fin-advisor-math"]
    
    def get_skill_metadata(skill_name):
        skill = mock_manager.skills.get(skill_name)
        return skill["metadata"] if skill else None
    mock_manager.get_skill_metadata.side_effect = get_skill_metadata
    
    def get_skill_directory(skill_name):
        skill = mock_manager.skills.get(skill_name)
        return skill["dir_path"] if skill else None
    mock_manager.get_skill_directory.side_effect = get_skill_directory
    
    def get_skill_content(skill_name):
        if skill_name == "csv-data-summarizer":
            return """---
name: csv-data-summarizer
description: CSV 数据分析与可视化
---

# CSV Data Summarizer

这是一个用于分析 CSV 数据的技能。

## 使用方法
1. 读取 CSV 文件
2. 分析数据结构
3. 生成可视化图表
"""
        elif skill_name == "fin-advisor-math":
            return """---
name: fin-advisor-math
description: 投顾场景的数学计算
---

# Financial Advisor Math

金融计算技能。
"""
        return f"Error: Skill '{skill_name}' not found"
    mock_manager.get_skill_content.side_effect = get_skill_content
    
    def get_skills_for_tool_description():
        lines = []
        for skill_name, skill_info in mock_manager.skills.items():
            desc = skill_info["metadata"].get("description", "No description")
            lines.append(f"- {skill_name}: {desc}")
        return "\n".join(lines)
    mock_manager.get_skills_for_tool_description.side_effect = get_skills_for_tool_description
    
    return mock_manager


# ============================================
# 测试用例
# ============================================
def test_skill_tool_attributes():
    """测试 SkillTool 基本属性"""
    print("\n[TEST 1] SkillTool 基本属性")
    
    mock_manager = create_mock_skill_manager()
    tool = SkillTool(mock_manager)
    
    # 验证 skill_injector 标识
    assert hasattr(tool, 'skill_injector'), "应该有 skill_injector 属性"
    assert tool.skill_injector == True, "skill_injector 应为 True"
    print(f"  - skill_injector: {tool.skill_injector}")
    
    # 验证工具名称
    assert tool.name == "Skill", f"工具名称应为 'Skill'，实际为 '{tool.name}'"
    print(f"  - name: {tool.name}")
    
    # 验证不是 client_side 工具
    assert getattr(tool, 'client_side', False) == False, "不应该是 client_side 工具"
    print(f"  - client_side: {getattr(tool, 'client_side', False)}")
    
    print("  [PASS]")


def test_skill_tool_parameters():
    """测试 SkillTool 参数定义"""
    print("\n[TEST 2] SkillTool 参数定义")
    
    mock_manager = create_mock_skill_manager()
    tool = SkillTool(mock_manager)
    
    params = tool.parameters
    
    # 验证参数结构
    assert params["type"] == "object"
    assert "skill" in params["properties"], "应该有 skill 参数"
    assert "args" in params["properties"], "应该有 args 参数"
    
    # 验证 skill 是必填
    assert "skill" in params.get("required", []), "skill 应该是必填参数"
    
    print(f"  - properties: {list(params['properties'].keys())}")
    print(f"  - required: {params.get('required', [])}")
    
    # 验证函数定义格式
    func_def = tool.to_function_definition()
    assert func_def["type"] == "function"
    assert func_def["function"]["name"] == "Skill"
    print(f"  - function definition name: {func_def['function']['name']}")
    
    print("  [PASS]")


def test_skill_tool_description():
    """测试 SkillTool description 动态生成"""
    print("\n[TEST 3] SkillTool description 动态生成")
    
    mock_manager = create_mock_skill_manager()
    tool = SkillTool(mock_manager)
    
    desc = tool.description
    
    # 验证包含模板内容
    assert "Load a specialized skill" in desc, "应包含模板开头"
    assert "Available skills:" in desc, "应包含 'Available skills:' 标记"
    
    # 验证包含技能清单
    assert "csv-data-summarizer" in desc, "应包含 csv-data-summarizer 技能"
    assert "fin-advisor-math" in desc, "应包含 fin-advisor-math 技能"
    assert "CSV 数据分析与可视化" in desc, "应包含技能描述"
    
    # 验证包含控制指令
    assert "IMMEDIATELY" in desc, "应包含 IMMEDIATELY 控制指令"
    assert "NEVER skip this tool" in desc, "应包含禁止跳过的指令"
    
    print(f"  - description 长度: {len(desc)} 字符")
    print(f"  - 包含技能清单: [OK]")
    print(f"  - 包含控制指令: [OK]")
    
    print("  [PASS]")


def test_skill_tool_execute_success():
    """测试 SkillTool.execute() 成功场景"""
    print("\n[TEST 4] SkillTool.execute() 成功场景")
    
    mock_manager = create_mock_skill_manager()
    tool = SkillTool(mock_manager)
    
    # 调用 execute
    result = tool.execute(skill="csv-data-summarizer", args="--verbose")
    
    # 验证返回格式
    assert result == "Launching skill: csv-data-summarizer", f"返回值应为 'Launching skill: csv-data-summarizer'，实际为 '{result}'"
    print(f"  - execute() 返回: {result}")
    
    # 验证内部状态被缓存
    assert tool._pending_skill == "csv-data-summarizer", "应缓存 skill 名称"
    assert tool._pending_args == "--verbose", "应缓存 args"
    print(f"  - _pending_skill: {tool._pending_skill}")
    print(f"  - _pending_args: {tool._pending_args}")
    
    print("  [PASS]")


def test_skill_tool_execute_not_found():
    """测试 SkillTool.execute() 技能不存在场景"""
    print("\n[TEST 5] SkillTool.execute() 技能不存在")
    
    mock_manager = create_mock_skill_manager()
    tool = SkillTool(mock_manager)
    
    # 调用不存在的技能
    result = tool.execute(skill="non-existent-skill")
    
    # 验证返回错误消息
    assert result.startswith("Error:"), f"应返回错误消息，实际为 '{result}'"
    assert "non-existent-skill" in result, "错误消息应包含技能名称"
    print(f"  - execute() 返回: {result}")
    
    print("  [PASS]")


def test_skill_tool_get_injection_content():
    """测试 SkillTool.get_injection_content()"""
    print("\n[TEST 6] SkillTool.get_injection_content()")
    
    mock_manager = create_mock_skill_manager()
    tool = SkillTool(mock_manager)
    
    # 先调用 execute 缓存状态
    tool.execute(skill="csv-data-summarizer", args="--output json")
    
    # 获取注入内容
    content = tool.get_injection_content()
    
    # 验证格式
    assert "Base directory for this skill:" in content, "应包含 Base directory"
    assert "Base directory for this skill: /workspace/skills/csv-data-summarizer" in content
    assert "CSV Data Summarizer" in content, "应包含 SKILL.md 内容"
    assert "ARGUMENTS:" in content, "应包含 ARGUMENTS 段"
    assert "--output json" in content, "应包含传入的参数"
    
    print(f"  - 注入内容长度: {len(content)} 字符")
    print(f"  - 包含 Base directory: [OK]")
    print(f"  - 包含 SKILL.md 内容: [OK]")
    print(f"  - 包含 ARGUMENTS: [OK]")
    
    # 打印前 200 字符
    print(f"  - 内容预览:\n{content[:200]}...")
    
    print("  [PASS]")


def test_skill_tool_get_injection_content_no_args():
    """测试 SkillTool.get_injection_content() 无参数场景"""
    print("\n[TEST 7] SkillTool.get_injection_content() 无参数")
    
    mock_manager = create_mock_skill_manager()
    tool = SkillTool(mock_manager)
    
    # 调用 execute 不传 args
    tool.execute(skill="fin-advisor-math")
    
    # 获取注入内容
    content = tool.get_injection_content()
    
    # 验证 ARGUMENTS 显示 (none)
    assert "ARGUMENTS: (none)" in content, "无参数时应显示 '(none)'"
    print(f"  - ARGUMENTS 段: ARGUMENTS: (none)")
    
    print("  [PASS]")


def test_skill_manager_get_skills_for_tool_description():
    """测试 SkillManager.get_skills_for_tool_description()"""
    print("\n[TEST 8] SkillManager.get_skills_for_tool_description()")
    
    # 使用真实的 SkillManager（如果 skills 目录存在）
    skills_dir = Path(__file__).parent.parent / "skills"
    
    if skills_dir.exists():
        manager = SkillManager(skills_dir)
        result = manager.get_skills_for_tool_description()
        
        print(f"  - 实际技能目录: {skills_dir}")
        print(f"  - 返回内容:\n{result}")
        
        # 验证格式
        if result:
            lines = result.strip().split("\n")
            for line in lines:
                assert line.startswith("- "), f"每行应以 '- ' 开头: {line}"
                assert ": " in line, f"每行应包含 ': ' 分隔符: {line}"
            print(f"  - 格式验证: [OK] ({len(lines)} 个技能)")
        else:
            print(f"  - 无技能，返回空字符串")
    else:
        print(f"  - 跳过（skills 目录不存在: {skills_dir}）")
        print(f"  - 使用 Mock 测试")
        
        mock_manager = create_mock_skill_manager()
        result = mock_manager.get_skills_for_tool_description()
        
        assert "csv-data-summarizer" in result
        assert "fin-advisor-math" in result
        print(f"  - Mock 返回:\n{result}")
    
    print("  [PASS]")


def test_skill_manager_get_skill_content():
    """测试 SkillManager.get_skill_content()"""
    print("\n[TEST 9] SkillManager.get_skill_content()")
    
    skills_dir = Path(__file__).parent.parent / "skills"
    
    if skills_dir.exists():
        manager = SkillManager(skills_dir)
        skills = manager.list_skills()
        
        if skills:
            skill_name = skills[0]
            content = manager.get_skill_content(skill_name)
            
            print(f"  - 测试技能: {skill_name}")
            print(f"  - 内容长度: {len(content)} 字符")
            
            # 验证内容
            assert len(content) > 0, "内容不应为空"
            assert "---" in content or "#" in content, "应包含 YAML frontmatter 或 Markdown 标题"
            print(f"  - 内容预览:\n{content[:150]}...")
        else:
            print(f"  - 无技能可测试")
    else:
        print(f"  - 跳过（skills 目录不存在）")
        print(f"  - 使用 Mock 测试")
        
        mock_manager = create_mock_skill_manager()
        content = mock_manager.get_skill_content("csv-data-summarizer")
        
        assert "CSV Data Summarizer" in content
        print(f"  - Mock 内容:\n{content[:150]}...")
    
    print("  [PASS]")


def test_tool_registry_skill_tool():
    """测试 ToolRegistry 中注册 SkillTool"""
    print("\n[TEST 10] ToolRegistry 注册 SkillTool")
    
    mock_manager = create_mock_skill_manager()
    
    registry = ToolRegistry()
    skill_tool = SkillTool(mock_manager)
    registry.register(skill_tool)
    
    # 验证注册
    assert "Skill" in registry.tools, "应该注册 Skill 工具"
    print(f"  - 已注册工具: {list(registry.tools.keys())}")
    
    # 验证获取
    tool = registry.get("Skill")
    assert tool is not None
    assert tool.skill_injector == True
    print(f"  - registry.get('Skill').skill_injector: {tool.skill_injector}")
    
    # 验证工具定义
    definitions = registry.get_all_definitions()
    tool_names = [d["function"]["name"] for d in definitions]
    assert "Skill" in tool_names
    print(f"  - 工具定义中包含 Skill: [OK]")
    
    print("  [PASS]")


def test_mock_skill_injection_flow():
    """模拟 skill_injector 注入流程（不实际调用 LLM）"""
    print("\n[TEST 11] 模拟 skill_injector 注入流程")
    
    mock_manager = create_mock_skill_manager()
    tool = SkillTool(mock_manager)
    
    # 模拟工具调用参数
    tool_call = {
        "id": "call_abc123",
        "function": {
            "name": "Skill",
            "arguments": json.dumps({"skill": "csv-data-summarizer", "args": ""})
        }
    }
    
    tool_args = json.loads(tool_call["function"]["arguments"])
    
    # 模拟 core.py 中的处理逻辑
    conversation_history = []
    
    # 检测是否为 skill_injector
    if getattr(tool, 'skill_injector', False):
        print(f"  - 检测到 skill_injector 工具")
        
        # 1. 执行工具
        result_str = tool.execute(**tool_args)
        print(f"  - execute() 返回: {result_str}")
        
        # 检查是否成功
        if not result_str.startswith("Error:"):
            # 2. 添加 tool 响应
            conversation_history.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "name": "Skill",
                "content": result_str
            })
            print(f"  - 添加 tool 消息: {result_str}")
            
            # 3. 添加桥接 assistant 消息
            conversation_history.append({
                "role": "assistant",
                "content": ""  # 空字符串
            })
            print(f"  - 添加桥接 assistant 消息: (empty)")
            
            # 4. 注入 user 消息
            injection_content = tool.get_injection_content()
            conversation_history.append({
                "role": "user",
                "content": injection_content
            })
            print(f"  - 添加 user 注入消息: ({len(injection_content)} 字符)")
    
    # 验证消息顺序
    assert len(conversation_history) == 3, f"应有 3 条消息，实际 {len(conversation_history)}"
    assert conversation_history[0]["role"] == "tool"
    assert conversation_history[1]["role"] == "assistant"
    assert conversation_history[2]["role"] == "user"
    
    print(f"\n  - 消息顺序验证:")
    for i, msg in enumerate(conversation_history):
        content_preview = msg["content"][:50] if msg["content"] else "(empty)"
        print(f"    [{i+1}] {msg['role']}: {content_preview}...")
    
    # 验证消息内容
    assert conversation_history[0]["content"] == "Launching skill: csv-data-summarizer"
    assert conversation_history[1]["content"] == ""  # 桥接消息为空
    assert "Base directory for this skill:" in conversation_history[2]["content"]
    assert "CSV Data Summarizer" in conversation_history[2]["content"]
    
    print(f"\n  - 内容验证: [OK]")
    print("  [PASS]")


def test_core_skill_injector_detection():
    """测试 core.py 中 skill_injector 检测逻辑（源码检查）"""
    print("\n[TEST 12] core.py skill_injector 检测逻辑")
    
    core_path = Path(__file__).parent.parent / "agent_system" / "agent" / "core.py"
    
    if core_path.exists():
        source = core_path.read_text(encoding="utf-8")
        
        # 验证 skill_injector 相关代码
        checks = [
            ("skill_injector 属性检测", "getattr(tool, 'skill_injector', False)"),
            ("tool 响应添加", '"role": "tool"'),
            ("桥接 assistant 消息", '"role": "assistant"'),
            ("user 注入消息", '"role": "user"'),
            ("get_injection_content 调用", "get_injection_content()"),
            ("skill_inject 事件", '"skill_inject"'),
            ("continue 跳过通用流程", "continue"),
        ]
        
        for desc, pattern in checks:
            if pattern in source:
                print(f"  - {desc}: [OK]")
            else:
                print(f"  - {desc}: [FAIL] (未找到 '{pattern}')")
                raise AssertionError(f"core.py 中未找到 '{pattern}'")
        
        print("  [PASS]")
    else:
        print(f"  - 跳过（core.py 不存在: {core_path}）")


# ============================================
# 测试运行器
# ============================================
def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Skill 工具单元测试: Phase1 Skill 工具引入与适配")
    print("=" * 60)
    
    tests = [
        test_skill_tool_attributes,
        test_skill_tool_parameters,
        test_skill_tool_description,
        test_skill_tool_execute_success,
        test_skill_tool_execute_not_found,
        test_skill_tool_get_injection_content,
        test_skill_tool_get_injection_content_no_args,
        test_skill_manager_get_skills_for_tool_description,
        test_skill_manager_get_skill_content,
        test_tool_registry_skill_tool,
        test_mock_skill_injection_flow,
        test_core_skill_injector_detection,
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
