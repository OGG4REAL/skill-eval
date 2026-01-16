# 复现 Claude Code Skills：基于 Docker MCP 沙盒的实现方案

> 本文档介绍如何从零复现 [Claude Code Agent Skills](https://code.claude.com/docs/en/skills) 的核心机制。

## 1. Claude Skills 核心设计理念

根据官方文档，Skills 系统有以下核心特点：

| 特点 | 说明 |
|------|------|
| **Model-Invoked** | Claude 根据用户请求自动判断需要哪个 Skill，无需用户显式调用 |
| **轻量级加载** | 启动时只加载 name + description，完整内容按需加载 |
| **Bash Runtime** | Agent 通过 bash 命令自由探索文件系统，主动学习技能文档和参考代码 |
| **沙盒执行** | 代码在隔离环境中运行，确保安全性 |

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                      宿主机                              │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Agent 核心                                         │  │
│  │  • LLM Client (DeepSeek/OpenAI)                   │  │
│  │  • SkillManager (只加载元数据)                     │  │
│  │  • BashTool / PythonTool                          │  │
│  └───────────────────────┬───────────────────────────┘  │
│                          │ MCP (stdio)                   │
└──────────────────────────┼──────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│                  Docker 容器（沙盒）                      │
│  • MCP Server: exec_command + run_python                │
│  • Volume 挂载:                                          │
│    /workspace/uploads  ← 用户上传文件                    │
│    /workspace/output   ← 生成的文件                      │
│    /workspace/skills   ← 技能文档（只读）                │
└──────────────────────────────────────────────────────────┘
```

### 为什么选择 Docker + MCP？

1. **安全隔离**：代码在容器内执行，`--network none` 断网，非 root 用户运行
2. **有状态 REPL**：容器持续运行，Python 变量跨调用保留（类似 Jupyter）
3. **统一通信**：MCP 协议通过 stdio 双向通信，简单可靠

---

## 3. 核心设计思路

### 3.1 三层加载机制

对齐 Claude Skills 的渐进式加载设计：

```
┌────────────────────────────────────────────────────────────────┐
│ Layer 1: 元数据                                                │
│ • 始终在 System Prompt 中                                      │
│ • 每个技能约 30-50 tokens                                      │
│ • 只有 name + description                                      │
│ • Agent 通过元数据判断需要哪个技能                             │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼ Agent 决定使用某技能
┌────────────────────────────────────────────────────────────────┐
│ Layer 2: SKILL.md                                              │
│ • Agent 主动执行 bash("cat skills/xxx/SKILL.md")              │
│ • 包含完整使用说明、参数要求、输出格式                         │
│ • 提及参考代码文件位置                                         │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼ Agent 需要学习实现模式
┌────────────────────────────────────────────────────────────────┐
│ Layer 3: 参考代码                                              │
│ • Agent 执行 bash("cat skills/xxx/analyze.py")                │
│ • 学习实现模式、最佳实践                                       │
│ • 注意代码中的 ⚠️ 注释（关键细节）                             │
└────────────────────────────────────────────────────────────────┘
```

**核心思想**：Agent 不是被动接收技能指令，而是**主动探索**文件系统，自己决定何时、读取什么内容。

### 3.2 Bash Runtime 设计

Agent 可以使用的 bash 命令（白名单）：

| 命令 | 用途 |
|------|------|
| `ls` | 列出目录，发现可用文件 |
| `cat` | 读取文件内容（SKILL.md、代码、配置） |
| `head/tail` | 预览大文件的开头/结尾 |
| `grep` | 搜索特定内容 |
| `find` | 查找文件位置 |
| `wc` | 统计行数 |

**安全限制**：
- 禁止 `rm`, `mv` 等修改命令
- 禁止管道 `|`、重定向 `>`、命令连接 `&&`
- Skills 目录只读挂载

### 3.3 有状态 Python REPL

Docker 容器内的 Python 执行器维护一个**全局上下文**，变量在多次调用间保留：

```
Call 1: import pandas; df = pd.read_csv('data.csv')
Call 2: print(df.head())           # df 仍然存在！
Call 3: df['new_col'] = df['a']*2  # 可以继续操作
Call 4: df.to_excel('output/result.xlsx')
```

这使得 Agent 可以像使用 Jupyter Notebook 一样分步执行复杂分析任务。

### 3.4 System Prompt 设计要点

System Prompt 需要告诉 Agent：

1. **目录结构**：文件在哪里（uploads/output/skills）
2. **工具用法**：bash 可以做什么，run_python_code 怎么用
3. **工作流程**：先读 SKILL.md → 再读参考代码 → 再执行任务
4. **关键提醒**：注意代码注释中的 ⚠️ 警告

---

## 4. Case Study：财务数据分析任务

### 任务输入

```
用户: 分析showcase文件
```

### 执行流程

| 阶段 | 轮次 | Agent 行为 | 对应机制 |
|------|------|-----------|---------|
| **探索** | 1-2 | `ls /workspace/` → `ls uploads/` | Bash Runtime |
| | | 发现 `showcase_financial_pl_data.csv` | |
| **预览** | 3-5 | `head -20 data.csv` → `wc -l` | 数据感知 |
| | | 了解 CSV 结构：45行×25列，财务数据 | |
| **学习** | 6 | `cat skills/csv-data-summarizer/SKILL.md` | **Layer 2** |
| | | 学到：使用加权比率而非简单平均 | |
| **学习** | 7 | `cat skills/csv-data-summarizer/analyze.py` | **Layer 3** |
| | | 学到：具体实现模式和代码结构 | |
| **执行** | 8-11 | 多次 `run_python_code` | 有状态 REPL |
| | | 加载数据 → 分析 → 生成图表 | |
| **输出** | 12-13 | 生成报告文件 + 总结 | |

### 关键观察

1. **自主学习**：Agent 在第 6-7 轮主动读取 SKILL.md 和参考代码，而非被动接收指令

2. **三层加载生效**：
   - System Prompt 只告诉 Agent "有个 csv-data-summarizer 技能"（Layer 1）
   - Agent 自己判断需要用它，主动读取完整文档（Layer 2-3）

3. **有状态执行**：
   - 第 8 轮：`df = pd.read_csv(...)`
   - 第 9 轮：直接使用 `df`（变量保留）
   - 第 10 轮：继续基于 `df` 做分析

4. **领域知识应用**：Agent 从 SKILL.md 学到"加权比率规则"，在分析中正确使用 `sum(profit)/sum(revenue)` 而非 `mean(margin)`

### 最终输出摘要

```
## 分析完成总结

### 关键财务指标（加权计算）
- 加权毛利率: 65.22%
- 加权净利润率: 13.21%

### 产品线分析
1. SaaS Platform: 收入占比 52.2%，净利率 16.37%（最佳）
2. Enterprise Solutions: 净利率 9.07%（需改进）
3. Professional Services: 净利率 11.2%

### 战略建议
1. 优先发展 SaaS Platform
2. 优化 Enterprise Solutions 成本结构
```

---

## 5. 与官方设计的对比

| 方面 | Claude Code Skills | 本项目实现 |
|------|-------------------|-----------|
| Skills 发现 | 启动时只加载元数据 | ✅ SkillManager 只提取 YAML frontmatter |
| Skills 加载 | Agent 按需通过 bash 读取 | ✅ bash("cat skills/...") |
| 文件探索 | Bash Runtime | ✅ 白名单命令 + 安全过滤 |
| 代码执行 | 沙盒环境 | ✅ Docker 容器 + 资源限制 |
| 有状态 REPL | 变量跨调用保留 | ✅ 全局上下文字典 |
| 安全隔离 | 网络隔离 + 权限限制 | ✅ --network none + 非 root |

---

## 6. 项目结构

```
csv-data-summarizer/
├── agent_system/
│   ├── agent/
│   │   ├── core.py          # Agent 主循环
│   │   ├── prompts.py       # System Prompt
│   │   └── memory.py        # 对话历史管理
│   ├── skills/manager.py    # 元数据加载（Layer 1）
│   └── tools/mcp_tools.py   # MCP Client + 工具实现
├── docker-sandbox/
│   ├── Dockerfile           # 沙盒镜像
│   └── server.py            # MCP Server
├── skills/
│   └── csv-data-summarizer/
│       ├── SKILL.md         # 技能定义（Layer 2）
│       └── analyze.py       # 参考代码（Layer 3）
└── sessions/<session-id>/
    ├── uploads/             # 用户上传
    ├── output/              # 生成文件
    └── chat.log             # 执行日志
```

---

## 参考资料

- [Claude Code Agent Skills 官方文档](https://code.claude.com/docs/en/skills)
- [MCP 协议规范](https://github.com/anthropics/mcp)

---

*文档更新：2024-12-30*
