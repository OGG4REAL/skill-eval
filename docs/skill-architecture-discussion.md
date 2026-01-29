# Claude Skills 架构深度讨论与实验验证

> 讨论日期：2025-01-19
> 主题：复刻 Claude Skills 的核心机制
>
> **重要说明**：本文档包含三部分内容：
> 1. **初始推测**：基于理解的架构推测（部分已验证为错误）
> 2. **实验发现**：通过两次实验验证的真实实现
>    - 实验 1：显式调用 (`/docx`)
>    - 实验 2：隐式调用（自然语言）

---

# Part 1: 实验发现 - Claude Skills 的真实实现

## 1.1 实验 1：显式调用

### 实验目标
通过实际调用 Claude skill (`/docx`) 来观察显式调用时的工作机制。

### 实验输入
```
用户: /docx 帮我写一个文档 标题是skill测试 内容是lets go Celtics
```

### 实际执行流程
1. Agent 收到 skill 内容
2. 读取参考文档 (`docx-js.md`, ~500行)
3. 创建 JavaScript 脚本
4. 安装依赖 (`npm install docx`)
5. 执行脚本生成 Word 文档
6. 验证结果 (`skill测试.docx`, 7.6 KB)

---

## 1.2 关键发现：Skill 注入的实际格式

### ❌ 错误推测（实验前）

我们之前推测会使用 XML 标签：
```xml
<command-name>/docx</command-name>
You are now operating under the /docx skill. Follow these instructions...
```

### ✅ 实际实现（实验验证）

实际收到的是**纯文本，无任何标签**：

```
Base directory for this skill: C:\Users\hywl\.claude\plugins\cache\anthropic-agent-skills\example-skills\69c0b1a06741\skills\docx

# DOCX creation, editing, and analysis

## Overview
A user may ask you to create, edit, or analyze the contents of a .docx file...
[完整的 Skill.md 内容，~500 行]

## Workflow Decision Tree
...

ARGUMENTS: create a document with title "skill测试" and content "lets go Celtics"
```

### 关键特征

| 特征 | 描述 |
|------|------|
| **格式** | 纯文本，无 XML/HTML 标签 |
| **结构** | Base directory → Skill 内容 → ARGUMENTS |
| **Base directory** | 提供技能文件路径，用于读取参考代码 |
| **ARGUMENTS** | 原始参数字符串（非 JSON） |

---

## 1.3 ARGUMENTS 生成机制

### 观察到的现象

**原始输入**：
```
/docx 帮我写一个文档 标题是skill测试 内容是lets go Celtics
```

**生成的 ARGUMENTS**：
```
ARGUMENTS: create a document with title "skill测试" and content "lets go Celtics"
```

### 推测的生成方式

```python
class ArgumentExtractor:
    """参数提取器（推测）"""

    def extract(self, user_input: str, skill_name: str) -> str:
        """
        从用户输入中提取并重写为清晰指令
        """
        # 使用主模型（Sonnet）重写用户输入
        prompt = f"""You are a parameter extractor for the {skill_name} skill.

User input: {user_input}

Extract the core task and rewrite it as a clear instruction.
Respond with: "ARGUMENTS: <instruction>"

Example:
Input: "帮我写一个文档 标题是测试 内容是hello"
Output: "ARGUMENTS: create a document with title '测试' and content 'hello'"

Now extract:"""

        return self.main_llm.call(prompt)
```

### 关键点

- **LLM 重写**：不是简单的模板匹配，而是用 LLM 理解意图后重写
- **结构化提取**：识别关键实体（标题、内容、文件名等）
- **英文指令**：即使输入是中文，ARGUMENTS 也转换为英文指令

---

## 1.4 工具返回的维护方式

### 实际的对话流结构

```python
conversation_history = [
    # 1. 系统注入 skill（作为 system 消息）
    {
        "role": "system",
        "content": """
Base directory for this skill: C:\\Users\\hywl\\.claude\\plugins\\cache\\...

# DOCX creation, editing, and analysis
...

ARGUMENTS: create a document with title "skill测试" and content "lets go Celtics"
"""
    },

    # 2. Assistant 读取参考文档
    {
        "role": "assistant",
        "content": "让我先读取 docx-js.md 参考文档...",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "bash",
                    "arguments": '{"command": "cat ...docx-js.md"}'
                }
            }
        ]
    },

    # 3. 工具返回（完整的 500+ 行文档内容）
    {
        "role": "tool",
        "tool_call_id": "call_1",
        "name": "bash",
        "content": "# DOCX Library Tutorial\n\nGenerate .docx files with JavaScript/TypeScript...\n\n[完整内容]"
    },

    # 4. Assistant 创建脚本
    {
        "role": "assistant",
        "tool_calls": [
            {
                "id": "call_2",
                "function": {
                    "name": "write_file",
                    "arguments": '{"path": "create_doc.js", "content": "const { Document..."}'
                }
            }
        ]
    },

    # 5. 工具返回（确认）
    {
        "role": "tool",
        "tool_call_id": "call_2",
        "name": "write_file",
        "content": "File created successfully"
    },

    # 6-9. [类似流程] 安装依赖、执行脚本...

    # 10. 最终回复
    {
        "role": "assistant",
        "content": "✅ Word 文档创建成功！\n\n文件：D:\\csv-data-summarizer\\skill测试.docx (7.6 KB)"
    }
]
```

### 关键特征

| 特征 | 描述 |
|------|------|
| **原始输出** | 工具返回完整的原始输出，不做预处理 |
| **独立消息** | 每个工具返回作为独立的 `tool` 消息 |
| **关联标识** | 通过 `tool_call_id` 关联到调用 |
| **可并行** | 一个 assistant 消息可包含多个 tool_calls |

---

## 1.5 Skill Offload 机制（推测）

### 观察到的行为

任务完成后，**没有收到明确的"退出 skill"指令**。

### 可能的实现方式

```python
class SkillLifecycleManager:
    """Skill 生命周期管理（推测）"""

    def check_should_offload(self,
                            conversation_history: List[Dict],
                            last_assistant_message: str) -> bool:
        """
        检查是否应该卸载 skill

        可能的判断依据：
        1. 任务完成信号检测
        2. 用户意图变化
        3. 新 skill 触发
        """

        # === 方案 1: 任务完成检测 ===
        if self._detect_task_completion(last_assistant_message):
            return True

        # === 方案 2: 用户意图变化 ===
        if self._detect_intent_shift(conversation_history):
            return True

        # === 方案 3: 新 skill 触发 ===
        # 用户输入了另一个 /skill 命令

        return False

    def _detect_task_completion(self, message: str) -> bool:
        """
        检测任务完成的信号

        Patterns:
        - "✅ 完成" / "成功" / "已创建"
        - 明确的结果展示（文件路径、输出摘要）
        """
        completion_indicators = [
            "✅", "完成", "成功", "已创建", "已生成",
            "Word 文档创建成功", "文件已保存"
        ]

        return any(indicator in message for indicator in completion_indicators)
```

### 推测：会话级持久化

从观察到的行为来看，更可能是：

```python
class ClaudeSkillManager:
    """Claude 的 Skill 管理（推测）"""

    def __init__(self):
        self.active_skill = None
        # 注意：没有时间阈值，没有轮次限制
        # Skill 一直存在，直到：
        # 1. 用户触发另一个 skill
        # 2. 用户明确说"完成"/"退出"
        # 3. 系统检测到完全无关的查询
```

---

## 1.6 上下文压缩策略（推测）

### 压缩原则

| 内容类型 | 是否压缩 | 说明 |
|---------|---------|------|
| **Skill 内容** | ❌ 不压缩 | 持久化在 system_prompt 中 |
| **对话历史** | ✅ 可能压缩 | 超过阈值时触发 |
| **关键结果** | ❌ 保护 | 重要工具输出不会被压缩 |

### 压缩实现（推测）

```python
class ContextManager:
    """上下文管理器（推测）"""

    def maybe_compress(self, conversation_history: List[Dict]) -> List[Dict]:
        """
        根据长度决定是否压缩
        """
        total_tokens = self._estimate_tokens(conversation_history)

        if total_tokens > CONTEXT_THRESHOLD:
            return self._compress_history(conversation_history)

        return conversation_history

    def _compress_history(self, history: List[Dict]) -> List[Dict]:
        """
        压缩策略：
        1. 保留最近的 N 轮完整对话
        2. 更早的对话压缩为摘要
        3. 保护关键内容（skill 文档、重要结果）
        """

        # 分离需要保护的内容
        protected = self._extract_protected(history)
        compressible = self._extract_compressible(history)

        # 压缩可压缩部分
        summary = self._generate_summary(compressible)

        # 重组
        return [
            {"role": "system", "content": summary},
            *protected,
            *compressible[-self.recent_window:]
        ]

    def _extract_protected(self, history: List[Dict]) -> List[Dict]:
        """
        提取需要保护的消息
        """
        protected = []

        for msg in history:
            # 1. Skill 注入消息（始终保留）
            if msg.get("role") == "system" and "Base directory" in msg.get("content", ""):
                protected.append(msg)
                continue

            # 2. 重要的工具结果（用户文件、最终输出）
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                if any(keyword in content for keyword in ["File created", "successfully", "完成"]):
                    protected.append(msg)
                    continue

        return protected
```

---

## 1.7 完整的对话流程图

```
用户输入: /docx 帮我写一个文档 标题是skill测试 内容是lets go Celtics
    ↓
[系统处理层] - 不可见
    ├─ 识别: 这是 /docx skill 调用
    ├─ 参数提取: "create a document with title 'skill测试' and content 'lets go Celtics'"
    └─ 注入: 将 skill 内容作为 system 消息插入
    ↓
[对话历史]
    ├─ system: [Base directory + 完整 skill 内容 + ARGUMENTS]
    ├─ assistant: [思考 + tool_calls]
    ├─ tool: [bash 返回 docx-js.md 内容]
    ├─ assistant: [tool_calls: write_file]
    ├─ tool: [确认写入]
    ├─ assistant: [tool_calls: bash npm install]
    ├─ tool: [npm 输出]
    ├─ assistant: [tool_calls: bash node script]
    ├─ tool: [成功]
    └─ assistant: [最终回复]
```

---

## 1.8 隐式调用实验 - 自然语言触发

### 实验目标

验证当用户使用自然语言（而非 `/skill-name` 命令）时，Claude 如何识别和选择 skill。

### 实验输入
```
用户: 帮我把skill测试.docx加一行beat lA
```

### 关键发现：系统不注入 Skill 内容

**观察结果**：系统**没有注入任何 skill 内容**！

与显式调用对比：

| 调用方式 | 收到的系统消息 |
|---------|---------------|
| **显式 (`/docx ...`)** | ```
Base directory for this skill: ...
# DOCX creation, editing, and analysis
...
ARGUMENTS: create a document...
``` |
| **隐式 (自然语言)** | **什么都没收到，只有用户原始输入** |

### Agent 如何知道要用 /docx skill？

**关键发现**：Agent 的基础 system prompt 中**始终包含所有 skills 的元数据列表**。

#### System Prompt 中的 Skill 元数据

```
<skills_library>
### docx
**Description**: Comprehensive document creation, editing, and analysis with support for tracked changes, comments, formatting preservation, and text extraction...

### pdf
**Description**: Comprehensive PDF manipulation toolkit...

### xlsx
**Description**: Comprehensive spreadsheet creation, editing, and analysis...

**NOTE**: The above are only lightweight metadata. You MUST read the full documentation in `/workspace/skills/` to use them correctly.
</skills_library>
```

#### Agent 的判断过程

```
工具调用 1: bash("file ...skill测试.docx")
    返回: "Microsoft Word 2007+"
    ↓
Agent 思考:
    "这是 Word 文档（.docx）"
    "我需要编辑它"
    "查阅 system prompt 中的 skills 元数据列表"
    "发现 docx skill: 'Comprehensive document creation, editing...'"
    "所以我应该去读取 /docx/SKILL.md"
    ↓
工具调用 2: bash("cat .../docx/SKILL.md | head -100")
```

### 完整的工具调用链

```
用户: 帮我把skill测试.docx加一行beat lA
    ↓
[系统层] - 完全静默，什么都没做
    ↓
Agent 收到: 只有用户原始输入
    ↓
Agent 判断: "需要编辑 Word 文档"
    ↓
工具调用 1: bash("file ...skill测试.docx")
    返回: "Microsoft Word 2007+"
    ↓
工具调用 2: bash("cat .../docx/SKILL.md | head -100")
    返回: [Skill 文档前 100 行]
    ↓
工具调用 3: bash("cat .../docx/ooxml.md | head -200")
    返回: [ooxml.md 前 200 行]
    ↓
工具调用 4-6: 寻找和定位文件
    ↓
工具调用 7: python unpack.py skill测试.docx unpacked
    返回: "Suggested RSID: 117CBE0B"
    ↓
工具调用 8-11: 编辑和打包
    ↓
最终回复: "任务完成！"
```

### 性能对比

| 维度 | 显式调用 (`/docx`) | 隐式调用 (自然语言) |
|------|-------------------|---------------------|
| **系统消息数** | 1 条（完整 Skill） | 0 条 |
| **工具调用次数** | 5 次 | 11 次 |
| **需要读取文档** | 1 次（docx-js.md） | 3 次（SKILL.md + ooxml.md + 部分） |
| **Agent 认知负担** | 低（被告诉做什么） | 高（自己判断 + 寻找） |
| **错误次数** | 0 次 | 4 次 |
| **执行效率** | 高 | 低 |

### 两层挂载机制

```
Layer 1 (启动时，持久化):
  - System prompt 包含所有 skills 的元数据
  - 格式：name + description
  - 作用：让 Agent 知道有哪些 skills 可用
  - 触发时机：始终存在，无论显式还是隐式调用

Layer 2 (运行时，动态注入):
  - 仅在显式调用时触发
  - 格式：Base directory + 完整内容 + ARGUMENTS
  - 作用：直接告诉 Agent 怎么做
  - 触发时机：用户输入 `/skill-name` 命令
```

### 关键结论

1. **元数据始终挂载**：无论显式还是隐式调用，system prompt 中都包含 skills 的元数据列表
2. **完整内容仅显式注入**：只有使用 `/skill-name` 时，系统才注入完整的 skill 内容
3. **隐式调用依赖自主判断**：Agent 需要根据元数据自己判断应该用哪个 skill
4. **你的实现完全正确**：你的 `SkillManager` 只加载元数据的做法与 Claude 的隐式调用模式完全一致

---

# Part 2: 架构对比 - 你的实现 vs Claude 实现

## 2.1 当前架构（你的项目）

### 工作流程

```
用户: "分析这个财务数据"
    ↓
Agent 判断: "看起来需要数据分析，我记得有个 csv-data-summarizer skill"
    ↓
Agent 调用: bash("cat skills/csv-data-summarizer/SKILL.md")
    ↓
Agent 阅读: 返回了 skill 内容
    ↓
Agent 理解: "好的，我看到了，要遵循加权比例规则..."
    ↓
Agent 执行: 按照理解执行
```

### 特征

| 维度 | 描述 |
|------|------|
| **触发方式** | Agent 自主判断 |
| **Skill 读取** | Agent 通过 bash 工具主动读取 |
| **Skill 位置** | 作为 tool 返回，混在对话历史中 |
| **参数提取** | 无（直接使用原始输入） |
| **Skill 持久化** | 依赖 Memory Manager 的保护机制 |

### 关键文件

- `agent_system/skills/manager.py` - 只加载元数据
- `agent_system/skills/loader.py` - 解析 SKILL.md
- `agent_system/agent/memory.py` - 保护 Skill 文档不被压缩

---

## 2.2 Claude 实现（基于实验）

### 工作流程（显式调用）

```
用户: /docx 帮我写一个文档...
    ↓
系统识别: Slash command 触发
    ↓
系统处理:
    ├─ 参数提取: LLM 重写为清晰指令
    └─ 内容注入: Base directory + Skill 内容 + ARGUMENTS
    ↓
对话历史:
    ├─ system: [完整 skill 内容]
    ├─ assistant: [执行任务]
    └─ tool: [工具返回]
```

### 特征

| 维度 | 描述 |
|------|------|
| **触发方式** | 用户显式调用（`/skill-name`） |
| **Skill 读取** | 系统直接注入，无需 Agent 读取 |
| **Skill 位置** | 作为独立的 system 消息 |
| **参数提取** | LLM 重写为英文指令 |
| **Skill 持久化** | 保持在 system_prompt 中 |

---

## 2.3 对比总结

| 维度 | 你的实现 | Claude 实现 |
|------|---------|------------|
| **触发方式** | Agent 自主判断 | 用户显式调用 (`/skill-name`) |
| **Skill 内容到达** | Agent bash 读取 | 系统 system 消息注入 |
| **是否使用标签** | 无 | 无（纯文本注入） |
| **Base directory** | 无 | ✅ 有（提供文件路径） |
| **ARGUMENTS** | 无 | ✅ 有（LLM 重写的指令） |
| **参数格式** | 原始输入 | 英文结构化指令 |
| **Agent 角色** | 主动探索者 | 被动接收者 |
| **Skill 持久化** | Memory Manager 保护 | System prompt 持久化 |
| **Offload 机制** | 无明确机制 | 任务完成检测（推测） |
| **上下文压缩** | Memory Manager | 独立的 Context Manager（推测） |

---

# Part 3: 实现建议

## 3.1 基于实验的改进方案

```python
class ClaudeLikeSkillInjector:
    """基于实验发现的 Skill 注入器"""

    def inject_skill(self, skill_name: str, user_args: str = "") -> str:
        """
        注入 skill 内容（模拟 Claude 的实际格式）

        Returns:
            完整的 skill 指令文本
        """
        # 1. 获取 skill 目录
        skill_dir = self.skill_manager.get_skill_directory(skill_name)

        # 2. 读取完整 SKILL.md
        skill_content = SkillLoader.load_full_skill(
            skill_dir / "SKILL.md"
        )

        # 3. 构建注入内容（按实际格式）
        injection = f"""Base directory for this skill: {skill_dir}

{skill_content}

ARGUMENTS: {user_args}
"""

        return injection
```

```python
class ArgumentExtractor:
    """参数提取器（基于实验推测）"""

    def extract(self, user_input: str, skill_name: str) -> str:
        """
        用 LLM 重写用户输入
        """
        prompt = f"""You are a parameter extractor for the {skill_name} skill.

User input: {user_input}

Extract the core task and rewrite it as a clear English instruction.
Respond with: "ARGUMENTS: <instruction>"

Example:
Input: "帮我写一个文档 标题是测试 内容是hello"
Output: "ARGUMENTS: create a document with title '测试' and content 'hello'"

Now extract:"""

        return self.main_llm.call(prompt)
```

```python
class SkillRouter:
    """Skill 路由器（用于显式调用）"""

    def route(self, user_input: str) -> Optional[tuple[str, str]]:
        """
        识别显式 skill 调用

        Returns:
            (skill_name, original_input) 或 None
        """
        # 检查是否是 slash command
        if user_input.startswith("/"):
            parts = user_input.split(None, 1)  # 分割为 /skill 和 args
            skill_name = parts[0][1:]  # 去掉 /
            args = parts[1] if len(parts) > 1 else ""

            return skill_name, args

        return None
```

```python
class AgentWithClaudeLikeSkills:
    """集成 Claude 风格 Skill 的 Agent"""

    def run(self, user_input: str):
        # 1. 检查显式 skill 调用
        route_result = self.skill_router.route(user_input)

        if route_result:
            skill_name, original_input = route_result

            # 2. 参数提取
            args_str = self.argument_extractor.extract(original_input, skill_name)

            # 3. 注入 skill
            skill_instruction = self.skill_injector.inject_skill(skill_name, args_str)

            # 4. 作为 system 消息插入
            self.conversation_history.append({
                "role": "system",
                "content": skill_instruction
            })

        # 5. 正常对话执行
        messages = [
            {"role": "system", "content": self.system_prompt}
        ] + self.conversation_history

        response = self.llm.chat(messages, tools=self.tools)
        # ...
```

---

## 3.2 兼容自主探索的混合方案

```python
class HybridSkillAgent:
    """混合式 Skill Agent（支持显式调用 + 自主探索）"""

    def run(self, user_input: str):
        # === 模式 1: 显式调用 ===
        explicit_route = self.explicit_router.route(user_input)

        if explicit_route:
            skill_name, original_input = explicit_route
            args_str = self.argument_extractor.extract(original_input, skill_name)

            # 直接注入 skill
            skill_instruction = self.skill_injector.inject_skill(skill_name, args_str)
            self.conversation_history.append({
                "role": "system",
                "content": skill_instruction
            })

        # === 模式 2: 自主探索（保持原有逻辑）===
        else:
            # 检查是否需要 skill（通过 LLM 判断）
            if self.should_use_skill(user_input):
                # 提示 Agent 去读取 skill
                # 依赖 Agent 的自主判断
                pass

        # 正常执行...
```

---

# Part 4: 待验证问题

## 4.1 Skill Offload 机制

**问题**：Skill 何时从 system_prompt 中移除？

**可能的答案**：
- [ ] 任务完成检测
- [ ] 用户意图变化
- [ ] 新 skill 触发
- [ ] 会话结束

**需要验证**：
- [ ] 实际触发 offload 的条件
- [ ] 是否有独立的判断模型

---

## 4.2 ARGUMENTS 生成

**问题**：ARGUMENTS 具体如何生成？

**可能的答案**：
- [x] LLM 重写（已验证）
- [ ] 模板匹配
- [ ] 两阶段处理（NER + 模板）

**需要验证**：
- [ ] 使用的 prompt 模板
- [ ] 是否有 fallback 机制

---

## 4.3 上下文压缩

**问题**：对话历史何时压缩？如何保护关键内容？

**可能的答案**：
- [ ] Token 阈值触发
- [ ] 轮次阈值触发
- [ ] 关键内容白名单

**需要验证**：
- [ ] 实际的压缩阈值
- [ ] 保护机制的精确实现

---

## 4.4 隐式 Skill 调用

**问题**：Claude 是否支持隐式 skill 调用（不使用 `/skill-name`）？

**可能的答案**：
- [ ] 支持（通过 LLM 判断）
- [ ] 不支持（只能显式调用）

**需要验证**：
- [ ] 在非专业用户场景下的行为

---

# Part 5: 附录

## 5.1 实验环境

### 实验 1：显式调用
- **日期**：2025-01-19 上午
- **Skill**：example-skills:docx
- **任务**：创建 Word 文档
- **输入**：`/docx 帮我写一个文档 标题是skill测试 内容是lets go Celtics`

### 实验 2：隐式调用
- **日期**：2025-01-19 下午
- **Skill**：example-skills:docx
- **任务**：编辑现有 Word 文档
- **输入**：`帮我把skill测试.docx加一行beat lA`

## 5.2 关键文件路径

- **Skill 目录**：`C:\Users\hywl\.claude\plugins\cache\anthropic-agent-skills\example-skills\69c0b1a06741\skills\docx`
- **参考文档**：`docx-js.md` (~500 行)
- **生成文件**：`skill测试.docx` (7.6 KB)

## 5.3 完整对话示例

### 显式调用对话流
参见第 1.4 节的完整对话流结构。

### 隐式调用对话流
参见第 1.8 节的完整工具调用链。

---

**文档版本**：v2.1
**最后更新**：2025-01-19
**更新内容**：
- ✅ 添加 1.8 节：隐式调用实验 - 自然语言触发
- ✅ 验证了两层挂载机制（元数据始终存在，完整内容仅显式注入）
- ✅ 对比了显式调用和隐式调用的性能差异
- ✅ 确认了用户项目的 `SkillManager` 实现完全正确
**状态**：基于两次实验验证的结论（显式 + 隐式），部分内容仍为推测
