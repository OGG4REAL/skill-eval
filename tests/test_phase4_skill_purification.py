"""
Phase 4 测试：Skill 净化 & 全局能力验证

测试目标：
1. prompts.py 中包含 UI 工具决策规则
2. Skill 文档已净化（无绘图代码、无旧协议）
3. Skill 明确声明"仅负责计算"
"""
import unittest
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPromptsUIDecisionRule(unittest.TestCase):
    """测试 prompts.py 中的 UI 工具决策规则"""
    
    def setUp(self):
        """读取 prompts.py 内容"""
        prompts_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'agent_system', 'agent', 'prompts.py'
        )
        with open(prompts_path, 'r', encoding='utf-8') as f:
            self.prompts_content = f.read()
    
    def test_client_side_ui_tools_section_exists(self):
        """测试是否包含 client_side_ui_tools 部分"""
        self.assertIn('<client_side_ui_tools>', self.prompts_content)
        self.assertIn('</client_side_ui_tools>', self.prompts_content)
    
    def test_ui_tools_listed(self):
        """测试是否列出所有 UI 工具"""
        self.assertIn('render_chart', self.prompts_content)
        self.assertIn('render_table', self.prompts_content)
        self.assertIn('show_notification', self.prompts_content)
    
    def test_ui_decision_rule_exists(self):
        """测试是否包含 UI 决策规则"""
        self.assertIn('UI Decision Rule', self.prompts_content)
        self.assertIn('MUST', self.prompts_content)
    
    def test_prohibits_matplotlib(self):
        """测试是否禁止使用 matplotlib"""
        self.assertIn('Do NOT generate matplotlib', self.prompts_content)
    
    def test_orchestrator_presentation_responsibility(self):
        """测试是否明确 Orchestrator 负责展示"""
        self.assertIn('Orchestrator', self.prompts_content)
        self.assertIn('PRESENTATION', self.prompts_content)


class TestFinAdvisorMathSkillPurification(unittest.TestCase):
    """测试 fin-advisor-math SKILL.md 净化"""
    
    def setUp(self):
        """读取 SKILL.md 内容"""
        skill_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'skills', 'fin-advisor-math', 'SKILL.md'
        )
        with open(skill_path, 'r', encoding='utf-8') as f:
            self.skill_content = f.read()
    
    def test_no_matplotlib_import(self):
        """测试不包含 matplotlib 导入"""
        self.assertNotIn('import matplotlib', self.skill_content)
        self.assertNotIn('from matplotlib', self.skill_content)
    
    def test_no_seaborn_import(self):
        """测试不包含 seaborn 导入"""
        self.assertNotIn('import seaborn', self.skill_content)
        self.assertNotIn('from seaborn', self.skill_content)
    
    def test_no_plt_savefig_in_code(self):
        """测试代码块中不包含 plt.savefig() 调用"""
        # 提取代码块内容
        lines = self.skill_content.split('\n')
        code_block_content = []
        in_code_block = False
        for line in lines:
            if line.startswith('```python') or line.startswith('```bash'):
                in_code_block = True
            elif line.startswith('```') and in_code_block:
                in_code_block = False
            elif in_code_block:
                code_block_content.append(line)
        
        code_content = '\n'.join(code_block_content)
        # 代码块中不应包含实际的 savefig 调用
        self.assertNotIn('plt.savefig(', code_content)
        self.assertNotIn('.savefig(', code_content)
    
    def test_no_old_analysis_result_protocol(self):
        """测试复杂场景示例不再手动构建图表 JSON"""
        # 检查是否移除了手动构建 charts 数组的代码
        self.assertNotIn('"charts": [{', self.skill_content)
    
    def test_computation_only_declaration(self):
        """测试是否声明仅负责计算"""
        self.assertIn('仅负责计算', self.skill_content)
        self.assertIn('不负责展示', self.skill_content)
    
    def test_orchestrator_ui_tools_reference(self):
        """测试是否引用 Orchestrator 的 UI 工具"""
        self.assertIn('render_chart', self.skill_content)
        self.assertIn('render_table', self.skill_content)


class TestCSVDataSummarizerSkillPurification(unittest.TestCase):
    """测试 csv-data-summarizer SKILL.md 净化"""
    
    def setUp(self):
        """读取 SKILL.md 内容"""
        skill_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'skills', 'csv-data-summarizer', 'SKILL.md'
        )
        with open(skill_path, 'r', encoding='utf-8') as f:
            self.skill_content = f.read()
    
    def test_no_analysis_result_start_marker(self):
        """测试不包含 ANALYSIS_RESULT_START 标记（已废弃）"""
        # 检查示例代码中不再使用此标记
        # 注意：可能在说明中提到它是 deprecated，所以检查是否不再作为指令
        lines = self.skill_content.split('\n')
        code_block_content = []
        in_code_block = False
        for line in lines:
            if line.startswith('```python'):
                in_code_block = True
            elif line.startswith('```') and in_code_block:
                in_code_block = False
            elif in_code_block:
                code_block_content.append(line)
        
        code_content = '\n'.join(code_block_content)
        self.assertNotIn('ANALYSIS_RESULT_START', code_content)
    
    def test_no_matplotlib_seaborn(self):
        """测试不包含 matplotlib/seaborn"""
        self.assertNotIn('import matplotlib', self.skill_content)
        self.assertNotIn('import seaborn', self.skill_content)
    
    def test_no_charts_array_in_output(self):
        """测试输出结构不包含 charts 数组（已移除）"""
        # 在 JSON Output Structure 中不应该有 charts 配置
        json_section_start = self.skill_content.find('## JSON Output Structure')
        visualization_section = self.skill_content.find('## Visualization Guidelines')
        
        if json_section_start != -1 and visualization_section != -1:
            json_section = self.skill_content[json_section_start:visualization_section]
            # charts 数组应该被移除，改为 data 结构
            self.assertIn('"data":', json_section)
    
    def test_computation_only_header(self):
        """测试头部声明仅负责计算"""
        self.assertIn('COMPUTATION ONLY', self.skill_content)
    
    def test_visualization_handled_by_orchestrator(self):
        """测试声明可视化由 Orchestrator 处理"""
        self.assertIn('VISUALIZATION IS HANDLED BY ORCHESTRATOR', self.skill_content)
        self.assertIn('render_chart', self.skill_content)
        self.assertIn('render_table', self.skill_content)
    
    def test_deprecated_markers_noted(self):
        """测试标注旧协议已废弃"""
        self.assertIn('deprecated', self.skill_content.lower())


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
    suite.addTests(loader.loadTestsFromTestCase(TestPromptsUIDecisionRule))
    suite.addTests(loader.loadTestsFromTestCase(TestFinAdvisorMathSkillPurification))
    suite.addTests(loader.loadTestsFromTestCase(TestCSVDataSummarizerSkillPurification))
    suite.addTests(loader.loadTestsFromTestCase(TestUIToolsIntegration))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 返回测试结果
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
