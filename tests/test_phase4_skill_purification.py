"""
Phase 4 测试：Skill 净化 & 执行策略验证

测试目标：
1. prompts.py 中包含 Write + Bash 审计留痕模式
2. fin-advisor-math SKILL.md 已更新为 Tier 1/Tier 2 执行策略
3. csv-data-summarizer SKILL.md 已更新为 Read→Write→Bash 工作流
4. analyze.py 使用 data 结构而非 charts 数组，无旧协议标记
5. UI 工具已注册且标记为 client_side
6. skill_tool.py 不再引用 run_python_code
"""
import unittest
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPromptsAuditTrailPattern(unittest.TestCase):
    """测试 prompts.py 中的 Write + Bash 审计留痕模式"""
    
    def setUp(self):
        """读取 prompts.py 内容"""
        prompts_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'agent_system', 'agent', 'prompts.py'
        )
        with open(prompts_path, 'r', encoding='utf-8') as f:
            self.prompts_content = f.read()
    
    def test_write_bash_audit_pattern_exists(self):
        """测试是否包含 Write + Bash 审计留痕模式说明"""
        self.assertIn('Write + Bash', self.prompts_content)
        self.assertIn('audit trail', self.prompts_content.lower())
    
    def test_bash_restricted_to_python(self):
        """测试是否说明 Bash 仅限执行 Python 脚本"""
        self.assertIn('python/python3', self.prompts_content)
    
    def test_specialized_tools_routing(self):
        """测试是否有专用工具路由指导"""
        self.assertIn('Read for reading files', self.prompts_content)
        self.assertIn('Write for creating/writing files', self.prompts_content)
        self.assertIn('List for listing directory contents', self.prompts_content)
    
    def test_no_run_python_code_reference(self):
        """测试 prompts.py 中不再引用 run_python_code"""
        self.assertNotIn('run_python_code', self.prompts_content)


class TestFinAdvisorMathTierStrategy(unittest.TestCase):
    """测试 fin-advisor-math SKILL.md 的 Tier 分层执行策略"""
    
    def setUp(self):
        """读取 SKILL.md 内容"""
        skill_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'skills', 'fin-advisor-math', 'SKILL.md'
        )
        with open(skill_path, 'r', encoding='utf-8') as f:
            self.skill_content = f.read()
    
    def test_tier1_cli_strategy_exists(self):
        """测试是否包含 Tier 1 CLI 直调策略"""
        self.assertIn('Tier 1', self.skill_content)
        self.assertIn('CLI', self.skill_content)
    
    def test_tier2_compose_strategy_exists(self):
        """测试是否包含 Tier 2 组合扩展策略"""
        self.assertIn('Tier 2', self.skill_content)
        self.assertIn('import', self.skill_content.lower())
    
    def test_no_run_python_code_reference(self):
        """测试不再引用 run_python_code"""
        self.assertNotIn('run_python_code', self.skill_content)
    
    def test_bash_pascalcase(self):
        """测试 Bash 使用 PascalCase"""
        # 示例中应使用 Bash(...) 而非 bash(...)
        self.assertIn('Bash("python', self.skill_content)
    
    def test_function_list_exists(self):
        """测试是否包含可用函数清单"""
        self.assertIn('可用函数清单', self.skill_content)
        self.assertIn('calc_aip_fv', self.skill_content)
        self.assertIn('calc_cagr', self.skill_content)
        self.assertIn('calc_irr', self.skill_content)
    
    def test_irr_in_cli_table(self):
        """测试 CLI 速查表包含 IRR"""
        self.assertIn('| **内部收益率** |', self.skill_content)
        self.assertIn('irr', self.skill_content.lower())
    
    def test_no_matplotlib_import(self):
        """测试不包含 matplotlib 导入指令"""
        self.assertNotIn('import matplotlib', self.skill_content)
    
    def test_computation_only_declaration(self):
        """测试是否声明仅负责计算"""
        self.assertIn('仅负责计算', self.skill_content)
        self.assertIn('不负责展示', self.skill_content)


class TestCSVDataSummarizerWorkflow(unittest.TestCase):
    """测试 csv-data-summarizer SKILL.md 的 Read→Write→Bash 工作流"""
    
    def setUp(self):
        """读取 SKILL.md 内容"""
        skill_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'skills', 'csv-data-summarizer', 'SKILL.md'
        )
        with open(skill_path, 'r', encoding='utf-8') as f:
            self.skill_content = f.read()
    
    def test_execution_strategy_section_exists(self):
        """测试是否包含执行策略部分"""
        self.assertIn('Execution Flow', self.skill_content)
    
    def test_read_write_bash_workflow(self):
        """测试是否包含 Read→Write→Bash 工作流"""
        self.assertIn('Read("uploads/', self.skill_content)
        self.assertIn('Write("temp/', self.skill_content)
        self.assertIn('Bash("python', self.skill_content)
    
    def test_reference_code_explanation(self):
        """测试是否说明参考代码的定位"""
        self.assertIn('Write("temp/analysis.py"', self.skill_content)
        self.assertIn('Bash("python temp/analysis.py")', self.skill_content)
    
    def test_anti_patterns_listed(self):
        """测试是否列出反模式"""
        self.assertIn('What NOT to do', self.skill_content)
        self.assertIn('python -c', self.skill_content)
    
    def test_deprecated_markers_noted(self):
        """测试是否标注旧协议已废弃"""
        self.assertNotIn('ANALYSIS_RESULT_START', self.skill_content)
        self.assertNotIn('ANALYSIS_RESULT_END', self.skill_content)
    
    def test_data_structure_not_charts(self):
        """测试输出结构说明使用 data 而非 charts"""
        # JSON Output Structure 部分应使用 "data" 而非 "charts"
        json_section_start = self.skill_content.find('## JSON Output Structure')
        if json_section_start != -1:
            json_section = self.skill_content[json_section_start:json_section_start + 1000]
            self.assertIn('"data":', json_section)
    
    def test_computation_only_header(self):
        """测试头部声明仅负责计算"""
        self.assertIn('UI Tools', self.skill_content)
        self.assertIn('render_chart', self.skill_content)
        self.assertIn('render_table', self.skill_content)


class TestAnalyzePyRefactoring(unittest.TestCase):
    """测试 analyze.py 的重构"""
    
    def setUp(self):
        """读取 analyze.py 内容"""
        analyze_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'skills', 'csv-data-summarizer', 'analyze.py'
        )
        with open(analyze_path, 'r', encoding='utf-8') as f:
            self.analyze_content = f.read()
    
    def test_no_analysis_result_markers(self):
        """测试不包含 ANALYSIS_RESULT_START/END 标记"""
        self.assertNotIn('ANALYSIS_RESULT_START', self.analyze_content)
        self.assertNotIn('ANALYSIS_RESULT_END', self.analyze_content)
    
    def test_uses_data_not_charts(self):
        """测试使用 data 结构而非 charts 数组"""
        self.assertIn('"data": {}', self.analyze_content)
        self.assertNotIn('"charts": []', self.analyze_content)
    
    def test_data_structure_assignments(self):
        """测试 data 结构赋值"""
        self.assertIn('result["data"]["revenue_trend"]', self.analyze_content)
        self.assertIn('result["data"]["margin_by_category"]', self.analyze_content)
        self.assertIn('result["data"]["revenue_composition"]', self.analyze_content)
    
    def test_no_charts_append(self):
        """测试不使用 charts.append()"""
        self.assertNotIn('result["charts"].append', self.analyze_content)
    
    def test_reference_implementation_header(self):
        """测试文件头说明参考实现定位"""
        self.assertIn('参考实现', self.analyze_content)
        self.assertIn('Reference Implementation', self.analyze_content)
    
    def test_np_encoder_exists(self):
        """测试 NpEncoder 类存在"""
        self.assertIn('class NpEncoder', self.analyze_content)


class TestFinanceFormulasUpdate(unittest.TestCase):
    """测试 finance_formulas.py 的更新"""
    
    def setUp(self):
        """读取 finance_formulas.py 内容"""
        formulas_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'skills', 'fin-advisor-math', 'scripts', 'finance_formulas.py'
        )
        with open(formulas_path, 'r', encoding='utf-8') as f:
            self.formulas_content = f.read()
    
    def test_no_setup_matplotlib_chinese(self):
        """测试已移除 setup_matplotlib_chinese 函数"""
        self.assertNotIn('def setup_matplotlib_chinese', self.formulas_content)
    
    def test_irr_cli_branch_exists(self):
        """测试 IRR CLI 分支存在"""
        self.assertIn("args.type == 'irr'", self.formulas_content)
        self.assertIn('--cashflows', self.formulas_content)
    
    def test_irr_in_epilog_example(self):
        """测试 epilog 中包含 IRR 示例"""
        self.assertIn('内部收益率:', self.formulas_content)
        self.assertIn('--type irr', self.formulas_content)


class TestSkillToolNoRunPythonCode(unittest.TestCase):
    """测试 skill_tool.py 不再引用 run_python_code"""
    
    def setUp(self):
        """读取 skill_tool.py 内容"""
        skill_tool_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'agent_system', 'tools', 'skill_tool.py'
        )
        with open(skill_tool_path, 'r', encoding='utf-8') as f:
            self.skill_tool_content = f.read()
    
    def test_no_run_python_code_reference(self):
        """测试不再引用 run_python_code"""
        self.assertNotIn('run_python_code', self.skill_tool_content)
    
    def test_uses_new_tool_names(self):
        """测试使用新的工具名称"""
        self.assertIn('Bash', self.skill_tool_content)
        self.assertIn('Read', self.skill_tool_content)
        self.assertIn('Write', self.skill_tool_content)
        self.assertIn('List', self.skill_tool_content)


class TestUIToolsIntegration(unittest.TestCase):
    """测试 UI 工具与 Agent 的集成"""
    
    def test_ui_tools_registered(self):
        """测试 UI 工具已在 agent_system 中注册"""
        from agent_system.tools.ui_tools import UI_TOOLS
        
        tool_names = [tool.name for tool in UI_TOOLS]
        self.assertIn('render_chart', tool_names)
        self.assertIn('render_table', tool_names)
        self.assertIn('show_notification', tool_names)
    
    def test_ui_tools_are_client_side(self):
        """测试所有 UI 工具标记为 client_side"""
        from agent_system.tools.ui_tools import UI_TOOLS
        
        for tool in UI_TOOLS:
            self.assertTrue(
                tool.client_side, 
                f"Tool {tool.name} should be marked as client_side"
            )


def run_tests():
    """运行所有测试"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加所有测试类
    suite.addTests(loader.loadTestsFromTestCase(TestPromptsAuditTrailPattern))
    suite.addTests(loader.loadTestsFromTestCase(TestFinAdvisorMathTierStrategy))
    suite.addTests(loader.loadTestsFromTestCase(TestCSVDataSummarizerWorkflow))
    suite.addTests(loader.loadTestsFromTestCase(TestAnalyzePyRefactoring))
    suite.addTests(loader.loadTestsFromTestCase(TestFinanceFormulasUpdate))
    suite.addTests(loader.loadTestsFromTestCase(TestSkillToolNoRunPythonCode))
    suite.addTests(loader.loadTestsFromTestCase(TestUIToolsIntegration))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 返回测试结果
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
