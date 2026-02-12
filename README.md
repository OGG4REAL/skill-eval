# Claude Skills Lab - Atomic Tools Edition

> **项目定位**：复现 Claude Skills 核心模式的实验性 Agent 系统，通过 Docker MCP 沙盒实现可控的 Bash Runtime 和审计友好的 Python 执行环境。

## 核心架构 (v2.0 原子工具基座)

### 三层加载机制（Claude Skills 复现）

1. **Layer 1 - 元数据加载**：启动时扫描 `skills/*/SKILL.md`，仅解析 YAML frontmatter（name, description, metadata），不加载完整内容
2. **Layer 2 - 按需探索**：Agent 通过 `Read("skills/xxx/SKILL.md")` 自主读取完整技能文档
3. **Layer 3 - 代码参考**：Agent 通过 `Read("skills/xxx/analyze.py")` 读取参考代码片段（Few-Shot Learning）

### 原子化工具体系 (Audit-Friendly)

为了满足金融级审计要求，v2.0 移除了不透明的内存 REPL (`run_python_code`)，转而采用 **"Write + Bash"** 的留痕模式：所有执行的代码必须先写入文件，再通过 Python 解释器执行。

- **Read**: 读取文件（带分页、自动截断保护、编码识别）
- **Write**: 写入文件（自动创建目录、1MB 大小限制、审计留痕）
- **List**: 列出目录（带分页、递归支持）
- **Bash**: 执行 Python 脚本（仅限 `python/python3`，禁止其他 Shell 命令）

### Web 模式资源管理

- **CleanupTTLCache**: 自定义缓存策略，确保会话过期时自动触发 Docker 容器清理
- **Auto-Cleanup**: 定时器后台巡检，防止僵尸容器泄漏

## 目录结构

```
csv-data-summarizer/
├── agent_system/             # Agent 核心系统
│   ├── agent/                # Agent 主循环与提示词
│   ├── skills/               # Skill 元数据管理
│   └── tools/                # 工具层适配 (MCPClient, BashTool, ReadTool...)
├── docker-sandbox/           # MCP Server (server.py) + Dockerfile
├── server/                   # FastAPI 后端 + CopilotKit Adapter
├── frontend/                 # React 前端 (CopilotKit 风格)
├── skills/                   # 技能定义 (Tier 1/Tier 2 策略)
│   ├── csv-data-summarizer/  # CSV 分析技能 (代码模板模式)
│   └── fin-advisor-math/     # 金融计算技能 (Tier 1/Tier 2 分层模式)
├── sessions/                 # 会话数据 (uploads/output/temp)
├── tests/                    # 测试套件 (158+ 单元测试)
└── docs/                     # 设计文档 (atomic_tool_redesign.md)
```

## 开发约定

### 1. 技能开发模式 (v2.0 新增)

#### 模式 A: Tier 1 / Tier 2 分层策略 (适用于确定性计算)
以 `fin-advisor-math` 为例：
- **Tier 1 (CLI 直调)**: 标准场景直接调用脚本 `Bash("python scripts/finance.py --type aip ...")`
- **Tier 2 (组合扩展)**: 复杂场景通过 `import` 复用已有函数库，编写组合脚本 `Write(...)` -> `Bash(...)`

#### 模式 B: 代码模板模式 (适用于探索性分析)
以 `csv-data-summarizer` 为例：
- `analyze.py` 不作为 CLI 工具，而是作为 **参考实现 (Reference Implementation)**
- Agent 读取参考代码，学习 NpEncoder、加权比率计算等模式
- Agent 编写针对当前数据的分析脚本，风格与参考代码趋同

### 2. 审计留痕机制

所有动态代码执行必须遵循 **Write + Bash** 模式：

```python
# 1. 编写脚本 (留痕)
Write("temp/analysis_001.py", code_content)

# 2. 执行脚本 (审计)
Bash("python temp/analysis_001.py")
```

### 3. 计算 / 展示分离协议

**Skill 输出** → **Agent 调用 UI 工具** → **前端渲染**

- Skill 脚本输出结构化 JSON 数据 (包含 `data` 字段，**严禁**直接生成图片)
- Agent 根据数据结构调用 `render_chart` / `render_table`
- 前端组件负责最终渲染 (ECharts / Shadcn UI)

### 4. 安全限制

- **Bash 白名单**：仅允许 `python` 和 `python3` 命令，禁止管道 `|`、重定向 `>`、`rm` 等
- **文件系统沙箱**：所有操作限制在 `/workspace` 目录下
- **Skills 只读**：`skills/` 目录挂载为只读，防止被 Agent 篡改

## 运行方式

### 1. 环境准备

```bash
# Python 依赖
pip install -r requirements-agent.txt

# 前端依赖
cd frontend && npm install && cd ..

# 配置环境变量
cp env.example .env  # 设置 DEEPSEEK_API_KEY
```

### 2. 构建 Docker 沙盒

```bash
docker build -t claude-skills-sandbox:latest docker-sandbox
```

### 3. 启动服务

```bash
# 后端 API (Port 8000)
uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload

# 前端开发 (Port 5173)
cd frontend && npm run dev
```

### 4. CLI 调试模式

```bash
python -m agent_system.main "分析 uploads/test.csv"
```

## 测试验证

本项目包含完善的测试套件 (158+ Tests)，覆盖所有核心功能：

```bash
# Phase 1: Docker MCP Server 工具测试
python -m pytest tests/test_mcp_server_tools.py

# Phase 2: Python 端工具类测试
python -m pytest tests/test_mcp_tool_classes.py

# Phase 3: Web 模式资源清理测试
python -m pytest tests/test_cleanup_ttl_cache.py

# Phase 4: Skill 策略与净化测试
python -m pytest tests/test_phase4_skill_purification.py
```

## CopilotKit 集成现状

- ✅ **后端打通**: `/copilotkit/chat` SSE 接口已就绪，支持流式输出和工具调用
- 🚧 **前端闭环**: 目前使用自定义 SSE 解析，尚未完全接入 CopilotKit 标准 Runtime (Todo: 接入 `useCopilotReadable`)

## 参考文档

- [原子工具重构规划 (docs/atomic_tool_redesign.md)](docs/atomic_tool_redesign.md)
- [Claude Skills 官方文档](https://code.claude.com/docs/en/skills)
- [MCP 协议规范](https://github.com/anthropics/mcp)
