# Phase1：Skill 工具引入与适配清单

> 目标：对齐 Claude Code 的 Skill 工具机制，减少"找技能→读 SKILL.md"的轮次开销。

## 1. 范围与非范围

### 本阶段范围（必须做）
- 引入 `Skill` 工具（非 MCP、本地工具，标识为 `skill_injector`）。
- Skill 工具 description 内硬编码"可用技能清单"与核心调用约束。
- Skill 调用采用四步注入机制（见 2.1），确保 API 消息顺序兼容。
- 支持自然语言触发；一旦匹配技能，**必须先调用 Skill 工具**。

### 非范围（暂不做）
- 多技能匹配排序策略。
- 运行时保护规则（拦截 bash 直接读 SKILL.md 等）。
- 系统提示词的改造（单列到 Phase2 讨论）。
- `<command-name>` 标签检测（LLM 通过 description 自然学习）。

## 2. 目标行为（对齐 Claude Code）

### 2.1 Skill 工具调用的四步注入机制

为确保 OpenAI/DeepSeek API 消息顺序兼容，采用四步注入：

```
assistant(tool_call) → tool(Launching) → assistant(桥接) → user(技能注入)
```

**步骤分解：**

1) **assistant(tool_call)**：LLM 决定调用 Skill 工具
```json
{"role": "assistant", "tool_calls": [{"function": {"name": "Skill", "arguments": "{\"skill\": \"csv-data-summarizer\"}"}}]}
```

2) **tool(Launching)**：工具响应
```json
{"role": "tool", "content": "Launching skill: csv-data-summarizer"}
```

3) **assistant(桥接)**：解决 tool→user 的 API 顺序问题
```json
{"role": "assistant", "content": ""}
```

> **桥接消息策略（按优先级降级）**：
> - 优先级 1：空字符串 `""`（最干净，无上下文污染）
> - 优先级 2：单字符 `"."`（如果 API 不接受空字符串）
> - 优先级 3：`"..."`（省略号，语义极弱）
>
> 实现时先用空字符串测试，API 报错再降级。

4) **user(技能注入)**：完整技能内容
```json
{"role": "user", "content": "Base directory for this skill: /workspace/skills/csv-data-summarizer\n\n# CSV Data Summarizer\n<SKILL.md 全文>\n\nARGUMENTS: (none)"}
```

### 2.2 工具 description 中的控制语句

除技能清单外，description 必须包含以下控制指令（参照 Claude Code）：
- 若匹配到技能，必须**立即调用 Skill 工具**作为第一步。
- 禁止只提及技能名而不调用 Skill 工具。
- 仅允许调用 description 中列出的技能。
- 发现 `<command-name>` 标签表示技能已加载，不要重复调用。

### 2.3 Skill 工具 description 标准模板（对齐 Claude Code）

> 说明：除"可用技能清单"外，其余内容尽量与 Claude Code 原文保持一致。

```
Execute a skill within the main conversation

When users ask you to perform tasks, check if any of the available skills below can help complete the task more effectively. Skills provide specialized capabilities and domain knowledge.

When users ask you to run a "slash command" or reference "/<something>" (e.g., "/commit", "/review-pr"), they are referring to a skill. Use this tool to invoke the corresponding skill.

Example:
  User: "run /commit"
  Assistant: [Calls Skill tool with skill: "commit"]

How to invoke:
- Use this tool with the skill name and optional arguments
- Examples:
  - `skill: "pdf"` - invoke the pdf skill
  - `skill: "commit", args: "-m 'Fix bug'"` - invoke with arguments
  - `skill: "review-pr", args: "123"` - invoke with arguments
  - `skill: "ms-office-suite:pdf"` - invoke using fully qualified name

Important:
- When a skill is relevant, you must invoke this tool IMMEDIATELY as your first action
- NEVER just announce or mention a skill in your text response without actually calling this tool
- This is a BLOCKING REQUIREMENT: invoke the relevant Skill tool BEFORE generating any other response about the task
- Only use skills listed in "Available skills" below
- Do not invoke a skill that is already running
- Do not use this tool for built-in CLI commands (like /help, /clear, etc.)
- If you see a <command-name> tag in the current conversation turn (e.g., <command-name>/commit</command-name>), the skill has ALREADY been loaded and its instructions follow in the next message. Do NOT call this tool - just follow the skill instructions directly.

Available skills:
- <skill-name-1>: <description>
- <skill-name-2>: <description>
```

## 3. 需要适配的模块清单

### 3.1 `agent_system/tools/skill_tool.py`（新增文件）
- 新增 `SkillTool` 类（继承 `BaseTool`）。
- 类属性 `skill_injector = True`，用于 `core.py` 识别并触发注入流程。
- Tool schema：`skill`（必填，字符串）、`args`（可选，字符串）。
- Tool description：调用 `SkillManager.get_skills_for_tool_description()` 拼接模板。

**方法设计（职责分离）**：
- `execute(skill, args)` → 返回 `str`：工具响应内容（`"Launching skill: xxx"`），兼容 ToolRegistry 通用流程。
- `get_injection_content()` → 返回 `str`：待注入的 user 消息内容，供 core.py 在注入阶段调用。

```python
class SkillTool(BaseTool):
    skill_injector = True
    
    def __init__(self, skill_manager: SkillManager):
        self.skill_manager = skill_manager
        self._pending_skill: str = ""
        self._pending_args: str = ""
    
    def execute(self, skill: str, args: str = "") -> str:
        """工具执行：返回 tool 响应内容"""
        # 验证技能存在
        if not self.skill_manager.get_skill_metadata(skill):
            return f"Error: Skill '{skill}' not found"
        
        # 缓存参数供后续注入使用
        self._pending_skill = skill
        self._pending_args = args
        
        return f"Launching skill: {skill}"
    
    def get_injection_content(self) -> str:
        """获取待注入的 user 消息内容"""
        skill_name = self._pending_skill
        skill_dir = self.skill_manager.get_skill_directory(skill_name)
        skill_content = self.skill_manager.get_skill_content(skill_name)
        
        return f"""Base directory for this skill: {skill_dir}

{skill_content}

ARGUMENTS: {self._pending_args or '(none)'}"""
```

### 3.2 `agent_system/skills/manager.py`
- **新增** `get_skills_for_tool_description()` 方法：返回简洁列表格式（用于 Tool description）。
  ```python
  def get_skills_for_tool_description(self) -> str:
      """返回 Skill 工具 description 所需的技能清单格式"""
      lines = []
      for skill_name, skill_info in self.skills.items():
          desc = skill_info['metadata'].get('description', 'No description')
          lines.append(f"- {skill_name}: {desc}")
      return "\n".join(lines)
  ```
- **新增** `get_skill_content(skill_name)` 方法：读取并返回完整 SKILL.md 内容。
  ```python
  def get_skill_content(self, skill_name: str) -> str:
      """读取并返回技能的完整 SKILL.md 内容"""
      skill = self.skills.get(skill_name)
      if not skill:
          return f"Error: Skill '{skill_name}' not found"
      
      skill_file = skill['file_path']
      return skill_file.read_text(encoding='utf-8')
  ```
- 保持现有元数据扫描逻辑不变。

### 3.3 `agent_system/agent/core.py`
识别 `SkillTool` 的工具调用结果，执行四步注入流程。

**关键设计**：skill_injector 工具需要**绕过通用的 result_str 处理**，避免返回值被错误序列化。

```python
# 在工具执行循环中添加 SkillTool 特殊分支（位于 client_side 判断之前）
if tool and getattr(tool, 'skill_injector', False):
    # 1. 执行工具，获取 tool 响应
    result_str = tool.execute(**tool_args)
    
    # 检查是否执行成功（不是 Error 开头）
    if result_str.startswith("Error:"):
        # 技能不存在，走正常的 tool 响应流程
        self.conversation_history.append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "name": tool_name,
            "content": result_str
        })
        continue
    
    # 2. 添加 tool 响应消息
    self.conversation_history.append({
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "name": tool_name,
        "content": result_str  # "Launching skill: xxx"
    })
    
    # 3. 添加桥接 assistant 消息（优先空字符串，报错再降级）
    self.conversation_history.append({
        "role": "assistant",
        "content": ""  # 降级方案: "." 或 "..."
    })
    
    # 4. 获取并注入 user 消息（技能内容）
    injection_content = tool.get_injection_content()
    self.conversation_history.append({
        "role": "user",
        "content": injection_content
    })
    
    # 5. 记录日志
    skill_name = tool._pending_skill
    _emit("skill_inject", f"技能 {skill_name} 已注入")
    execution_log.append(f"  技能注入: {skill_name}")
    console.print(f"  [cyan]技能 {skill_name} 已注入到上下文[/cyan]")
    
    # 跳过后续的通用处理，继续下一个工具调用
    continue

elif tool and getattr(tool, 'client_side', False):
    # 客户端工具处理（保持原有逻辑）
    ...
else:
    # 通用工具处理（保持原有逻辑）
    ...
```

历史顺序固定为：
```
assistant(tool_call) → tool(Launching) → assistant(桥接) → user(技能注入) → 下一轮 LLM
```

日志中记录注入动作与技能名称（便于审计）。

### 3.4 `agent_system/main.py`
- 工具注册流程中加入 `SkillTool`（需要传入 `SkillManager` 引用）。
- 启动日志打印"已注册 Skill 工具"。

```python
# 在 UI 工具注册之前添加
from .tools.skill_tool import SkillTool

skill_tool = SkillTool(skill_manager)
tool_registry.register(skill_tool)
console.print(f"  [green]✓[/green] {skill_tool.name:20s} - 技能加载与注入")
```

## 4. 运行流程（文本版）

1. 用户自然语言输入。
2. 模型根据 Skill 工具 description 中的技能清单选择 skill。
3. 模型调用 `Skill` 工具（tool_call）。
4. 工具执行 `execute()`，返回 `Launching skill: xxx`（tool 响应）。
5. **Agent 插入桥接 assistant 消息**（空字符串，或降级方案）。
6. **Agent 调用 `get_injection_content()` 获取技能内容，注入 user 消息**。
7. 模型收到技能内容后开始执行任务。

## 5. 验收标准

- 调用 Skill 时必然出现 "Launching skill: xxx"。
- 能在对话历史中看到"桥接 assistant 消息"和"技能内容的 user 消息注入"。
- 消息顺序符合 API 规范：`tool → assistant → user`。
- 桥接消息不污染上下文（优先空字符串）。
- 模型执行任务时不再需要 `bash("cat skills/.../SKILL.md")` 的中间轮次。

## 6. 备注（Phase2 待讨论）

- 系统提示词将移除或弱化 `<skills_library>` 元数据段。
- "先读 SKILL.md" 的提示将改为"先调用 Skill 工具"。
- 参考 Claude Code 其它工具描述写法做进一步统一。

---

## 7. 实现状态（已完成）

### 7.1 代码变更清单

| 文件 | 状态 | 说明 |
|------|------|------|
| `agent_system/tools/skill_tool.py` | **新增** | SkillTool 类，约 120 行 |
| `agent_system/skills/manager.py` | 修改 | 新增 2 个方法（+45 行） |
| `agent_system/agent/core.py` | 修改 | 新增 skill_injector 分支（+60 行） |
| `agent_system/main.py` | 修改 | 新增导入和注册（+5 行） |
| `tests/test_skill_tool.py` | **新增** | 单元测试，约 520 行 |

### 7.2 关键实现细节

**SkillTool 职责分离设计**：
- `execute()` 仅返回字符串 `"Launching skill: xxx"`，兼容 ToolRegistry 通用流程
- `get_injection_content()` 返回注入内容，由 core.py 单独调用
- 内部状态 `_pending_skill` / `_pending_args` 用于跨方法传递参数

**core.py 特判分支位置**：
- 位于 `client_side` 判断**之前**
- 使用 `continue` 跳过通用流程，避免返回值被 `str()` 序列化

**路径兼容性**：
- 注入内容中的路径使用 `Path` 对象，Windows 下显示为 `\`，Linux 下显示为 `/`
- 不影响功能，LLM 可正确识别

## 8. 单元测试结果

**测试文件**: `tests/test_skill_tool.py`
**运行命令**: `python tests/test_skill_tool.py`

### 8.1 测试覆盖

| # | 测试项 | 状态 | 说明 |
|---|--------|------|------|
| 1 | SkillTool 基本属性 | ✅ | `skill_injector=True`, `name="Skill"`, `client_side=False` |
| 2 | SkillTool 参数定义 | ✅ | `skill` 必填, `args` 可选 |
| 3 | description 动态生成 | ✅ | 包含技能清单 + 控制指令 (约 1600 字符) |
| 4 | execute() 成功场景 | ✅ | 返回 `"Launching skill: csv-data-summarizer"` |
| 5 | execute() 技能不存在 | ✅ | 返回 `"Error: Skill 'xxx' not found..."` |
| 6 | get_injection_content() | ✅ | 包含 Base dir + SKILL.md + ARGUMENTS |
| 7 | 无参数注入 | ✅ | `ARGUMENTS: (none)` |
| 8 | SkillManager.get_skills_for_tool_description() | ✅ | 返回 `- name: desc` 格式 |
| 9 | SkillManager.get_skill_content() | ✅ | 读取完整 SKILL.md (7201 字符) |
| 10 | ToolRegistry 注册 | ✅ | 正确注册和获取 |
| 11 | 模拟注入流程 | ✅ | 消息顺序: `tool → assistant → user` |
| 12 | core.py 源码检查 | ✅ | 包含所有必要的注入逻辑 |

### 8.2 测试输出摘要

```
============================================================
Skill 工具单元测试: Phase1 Skill 工具引入与适配
============================================================
[TEST 1] SkillTool 基本属性 ... [PASS]
[TEST 2] SkillTool 参数定义 ... [PASS]
[TEST 3] SkillTool description 动态生成 ... [PASS]
[TEST 4] SkillTool.execute() 成功场景 ... [PASS]
[TEST 5] SkillTool.execute() 技能不存在 ... [PASS]
[TEST 6] SkillTool.get_injection_content() ... [PASS]
[TEST 7] SkillTool.get_injection_content() 无参数 ... [PASS]
[TEST 8] SkillManager.get_skills_for_tool_description() ... [PASS]
[TEST 9] SkillManager.get_skill_content() ... [PASS]
[TEST 10] ToolRegistry 注册 SkillTool ... [PASS]
[TEST 11] 模拟 skill_injector 注入流程 ... [PASS]
[TEST 12] core.py skill_injector 检测逻辑 ... [PASS]
============================================================
测试结果: 12 通过, 0 失败
============================================================
```

## 9. 验收检查清单

供编排器验收时核对：

### 9.1 代码结构验收

- [ ] `agent_system/tools/skill_tool.py` 存在且包含 `SkillTool` 类
- [ ] `SkillTool.skill_injector == True`
- [ ] `SkillTool.name == "Skill"`
- [ ] `SkillTool.execute()` 返回 `"Launching skill: xxx"` 字符串
- [ ] `SkillTool.get_injection_content()` 返回包含 `Base directory` 的字符串

### 9.2 SkillManager 验收

- [ ] `get_skills_for_tool_description()` 方法存在
- [ ] 返回格式为 `- skill-name: description`（每行一个技能）
- [ ] `get_skill_content()` 方法存在
- [ ] 返回完整的 SKILL.md 文件内容

### 9.3 core.py 验收

- [ ] 包含 `getattr(tool, 'skill_injector', False)` 检测
- [ ] skill_injector 分支位于 client_side 分支**之前**
- [ ] 四步注入：`tool → assistant(桥接) → user(注入)`
- [ ] 桥接消息 content 为空字符串 `""`
- [ ] 使用 `continue` 跳过通用处理流程
- [ ] 发送 `skill_inject` 事件回调

### 9.4 main.py 验收

- [ ] 导入 `from .tools.skill_tool import SkillTool`
- [ ] 创建 `SkillTool(skill_manager)` 实例
- [ ] 注册到 `tool_registry`

### 9.5 功能验收（需 Phase2 完成后测试）

- [ ] LLM 能识别 Skill 工具并调用
- [ ] 技能内容正确注入到对话上下文
- [ ] 消息顺序符合 API 规范（无报错）
- [ ] 桥接消息不污染后续推理

## 10. 已知限制与后续改进

### 10.1 当前限制

1. **桥接消息兼容性未验证**：空字符串 `""` 是否被所有 API 接受需要集成测试验证
2. **系统提示词未改造**：当前提示词仍指导 LLM 用 `bash("cat ...")` 读取技能，需 Phase2 修改
3. **无防重复调用机制**：`<command-name>` 标签检测依赖 LLM 自行学习

### 10.2 Phase2 需完成

1. 修改系统提示词，移除 `<skills_library>` 段
2. 修改 `<critical_protocol>` 中的技能获取指令
3. 统一其他工具的 description 格式
4. 集成测试验证完整流程
