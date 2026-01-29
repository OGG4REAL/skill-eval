# Phase2：System Prompt 与工具描述改造规划

> 目标：将“规范与用法”从系统提示词下沉到工具 description，system prompt 保持轻量；对齐 Claude Code 的工具写法与调用理念（不改行为，仅改描述与结构）。

## 1. 范围与非范围

### 本阶段范围（必须做）
- 精简 system prompt：去除工具说明与技能清单，保留环境与流程。
- 改造工具 description（Skill / Bash / Python / UI 工具）以承载规则。
- 将 `client_side_ui_tools` 的使用规则迁移到 UI 工具 description。

### 非范围（暂不做）
- 改动工具权限/能力（如 Bash 白名单、MCP 接口等）。
- 多技能匹配排序策略与运行时保护规则。
- 前端或后端的协议格式调整。
- 桥接消息降级策略的实现（先在集成测试阶段验证，必要时再补）。

## 2. System Prompt 改造规划

### 2.1 结构调整
- 保留：`<role>`、`<language_requirements>`、`<environment>`。
- 新增：`<skills_access>`（强调“通过 Skill 工具获取技能内容”）。
- 精简：`<critical_protocol>` 中去掉“bash 读 SKILL.md”的硬性要求。
- 更新：`<thinking_process>`，改为“若匹配技能先调用 Skill 工具”。
- 移除：`<skills_library>`（技能清单转移至 Skill 工具 description）。
- 移除：`<tools_summary>` 与 `<client_side_ui_tools>`（规则下沉到工具 description）。

### 2.2 关键语义替换（概念级）
- 旧：If a task involves a skill → call `bash("cat skills/<name>/SKILL.md")`
- 新：If a task involves a skill → **invoke Skill tool first**, then follow injected instructions

## 3. 工具 description 改造规划

### 3.1 Skill 工具
- 使用 Phase1 中的 **CC 标准模板**（原文结构不改）。
- 可用技能清单放在 description 尾部。

### 3.2 Bash / Python 工具
- 采用 CC 结构化写法：用途、重要提示、执行步骤、示例。
- 强调与其他工具分工（文件操作优先用专用工具的原则）。
- 不改执行能力与限制（白名单/安全检查维持不变）。

#### Bash / Python 工具 description 参考文案（直接可用）

**bash**
```
执行命令行指令以探索文件系统与运行脚本。

重要提示：
- 优先使用专用工具完成文件操作：Read/Write/Edit/Glob/Grep
- 仅在确实需要终端执行时使用 bash
- 使用清晰简短的命令描述（5-10 个字），避免冗长叙述

使用建议：
- 需要探索目录或运行脚本时使用
- 对复杂命令补充意图描述
```

**run_python_code**
```
在有状态沙盒中执行 Python 代码（变量跨调用保留）。

重要提示：
- 适合复杂数据处理与自定义计算
- 优先使用已有脚本/技能指令中的推荐方式
- 需要产出文件时，将文件保存到输出目录

使用建议：
- 尽量写完整逻辑，减少拆分调用
```

### 3.3 UI 工具（render_chart / render_table / show_notification）
- 在各工具 description 中补充“使用决策规则”：
  - 趋势/时间序列 → `render_chart` line/area
  - 对比/排名 → `render_chart` bar
  - 占比/构成 → `render_chart` pie
  - 多维/相关性 → `render_chart` radar/scatter
  - 表格结果 >3 行 → `render_table`
  - 重要提示/警告 → `show_notification`
- 明确“客户端工具、无需等待结果”。

#### UI 工具 description 参考文案（直接可用）

**render_chart**
```
在前端渲染交互式图表（客户端工具，不在后端执行）。

使用场景：
- 趋势/时间序列 → line/area
- 对比/排名 → bar
- 占比/构成 → pie
- 多维/相关性 → radar/scatter

重要说明：
- 此工具为客户端渲染，调用后无需等待结果
- 图表类型必须与数据表达目标一致
```

**render_table**
```
在前端渲染交互式数据表格（客户端工具，不在后端执行）。

使用场景：
- 结构化结果需要完整展示
- 行数 > 3 或需要排序/筛选

重要说明：
- 此工具为客户端渲染，调用后无需等待结果
```

**show_notification**
```
在前端显示通知提示（客户端工具，不在后端执行）。

使用场景：
- 成功/警告/错误等重要提醒
- 需要吸引用户注意的关键信息

重要说明：
- 此工具为客户端渲染，调用后无需等待结果
```

## 4. 验收标准

- System prompt 中不再出现工具说明与技能清单。
- 技能相关规则通过 Skill 工具 description 生效。
- UI 决策规则从 system prompt 迁移到工具 description。
- 运行流程与 Phase1 相容，不影响实际执行能力。

## 5. Phase2 产出清单

- 更新 `agent_system/agent/prompts.py`（结构精简与语义替换）。
- 更新 `agent_system/tools/*.py` 的 tool description 文案（保持行为不变）。
- 可选：补充 `docs/` 中的工具描述规范文档（若需要对外说明）。

---

## 6. 代码审查：遗漏与调整建议

> 以下是基于代码现状的审查意见，供讨论确认。

### 6.1 计划与现状对照表

| 改造项 | 计划要求 | 当前状态 | 是否需要调整 |
|--------|----------|----------|--------------|
| `<role>` | 保留 | ✅ 存在 | 无需改动 |
| `<language_requirements>` | 保留 | ✅ 存在 | 无需改动 |
| `<environment>` | 保留 | ✅ 存在 | 无需改动 |
| `<skills_access>` | **新增** | ❌ 缺失 | **需要补充文案** |
| `<skills_library>` | **移除** | ❌ 还存在 | **需要移除** |
| `<critical_protocol>` | 精简 | ❌ 还有 bash 读 SKILL.md | **需要改写** |
| `<thinking_process>` | 更新 | ❌ 还是旧版 | **需要更新** |
| `<tools_summary>` | **移除** | ❌ 还存在 | **需要移除** |
| `<client_side_ui_tools>` | **移除** | ❌ 还存在 | **需要移除** |

### 6.2 遗漏项：调用链改造

`core.py` 第 60-61 行当前代码：

```python
self.skills_summary = skill_manager.get_skills_summary()
self.system_prompt = get_system_prompt(self.skills_summary, self._get_files_info())
```

如果移除 `<skills_library>`，`get_system_prompt()` 的签名和调用方都需要同步改动。

**建议补充到产出清单**：
- `prompts.py`: 函数签名调整 `get_system_prompt(skills_summary, ...)` → `get_system_prompt(files_info, ...)`
- `core.py`: 删除 `self.skills_summary` 相关代码，调整调用参数

### 6.3 遗漏项：`<skills_access>` 具体文案

计划中提到"新增 `<skills_access>`"，但没有给出参考内容。

**建议补充文案**：

```xml
<skills_access>
你拥有 Skill 工具（技能加载器），可按需获取技能详细指令。

使用方式：
- 当任务涉及技能时，**立即调用 Skill 工具**，技能文档将注入上下文
- 技能清单见 Skill 工具的 description，选择合适的技能名称即可
- 注入后按技能文档执行，无需手动 bash 读取 SKILL.md
</skills_access>
```

### 6.4 模糊项：`<critical_protocol>` 精简后的完整内容

当前 `<critical_protocol>` 有三条规则，计划只说"去掉 bash 读 SKILL.md"，其他条款是否保留未明确。

**建议明确精简后版本**：

```xml
<critical_protocol>
1. **效率优先**：
   - 数据探索使用高效命令，减少往返轮数
   - Python 代码尽量一次写完整逻辑，避免拆分多次调用

2. **输出渲染协议**：
   - 技能可能定义特定输出格式，必须严格遵循
   - 产出结构化数据时，优先使用 UI 工具（render_chart/render_table）
</critical_protocol>
```

原来的第 1 条"KNOWLEDGE ACQUISITION FIRST"整体移除（改由 `<skills_access>` + Skill 工具 description 承载）。

### 6.5 模糊项：中英文统一标准

Phase2 给的 Bash/Python description 参考文案是**中文**，但当前 `mcp_tools.py` 的 description 是**英文**。

**建议**：
- 按项目规范（`CLAUDE.md` 要求中文输出）统一改为中文
- 示例命令和技术术语保留英文

### 6.6 补充：UI 工具 description 改动范围

Phase2 给的 `render_chart` 等文案很简洁，但当前 `ui_tools.py` 中已有较详细的 `parameters` JSON Schema 描述。

**建议**：
- `description` 属性采用 Phase2 简洁文案
- `parameters` 中的字段描述保持现状（JSON Schema 不需要精简）

---

## 7. 更新后的产出清单（建议版）

```diff
 - 更新 agent_system/agent/prompts.py
+   - 函数签名调整：移除 skills_summary 参数
+   - 新增 <skills_access> 标签（参见 6.3 文案）
+   - 精简 <critical_protocol>（参见 6.4 文案）
+   - 更新 <thinking_process>
+   - 移除 <skills_library>、<tools_summary>、<client_side_ui_tools>
+
+ - 更新 agent_system/agent/core.py
+   - 移除 self.skills_summary 赋值
+   - 调整 get_system_prompt() 调用参数
+
 - 更新 agent_system/tools/*.py 的 tool description
+   - mcp_tools.py: BashTool.description（改为中文简洁版）
+   - mcp_tools.py: PythonTool.description（改为中文简洁版）
+   - ui_tools.py: 三个工具的 description（补充使用决策规则）
```

---

## 8. 更新后的验收标准（建议版）

```diff
 - System prompt 中不再出现工具说明与技能清单
+ - System prompt 中新增 <skills_access>，替代原有的 bash 读 SKILL.md 指令
+ - get_system_prompt() 函数签名简化，core.py 调用同步更新
 - 技能相关规则通过 Skill 工具 description 生效
 - UI 决策规则从 system prompt 迁移到工具 description
+ - 所有工具 description 统一使用中文（示例命令可保留英文）
 - 运行流程与 Phase1 相容，不影响实际执行能力
```
