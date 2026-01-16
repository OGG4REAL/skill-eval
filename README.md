# Claude Skills Lab

 本项目复现 Claude Skills 的核心模式：**三层加载**、**Bash Runtime**、**沙盒执行**、**技能自学习**，并通过 CopilotKit 风格的前端实现流式对话与 Generative UI。
 目标是在本地用 **Docker MCP 沙盒** 构建一个可扩展的“技能型 Agent”系统。

## 核心目标

- 复现 Claude Skills 的“按需加载 + 自主探索”机制
- 以 **MCP + Docker** 实现可控的 Bash Runtime 与有状态 Python REPL
- 技能只做计算，前端负责展示（图表、表格、通知）
- 前后端通路可联调：SSE 思考流 + UI 工具指令

## 架构概览

```
 用户前端
   └─ /copilotkit/chat (SSE)
         └─ server/copilot_adapter.py
               └─ Agent (agent_system)
                     ├─ SkillManager (仅元数据)
                     ├─ BashTool / PythonTool (MCP)
                     └─ UI Tools (client_side)
                           └─ 前端渲染 ECharts / Table / Notification
 
 MCP Client (宿主机)  <— stdio —>  Docker MCP Server (docker-sandbox/server.py)
```

## 复现 Claude Skills 的关键机制

1. **三层加载**

   - Layer 1：只加载 `SKILL.md` YAML 元数据（启动时）
   - Layer 2：Agent 按需 `cat skills/xxx/SKILL.md`
   - Layer 3：Agent 按需读取参考代码（如 `analyze.py`）
2. **Bash Runtime（MCP + Docker）**

   - `bash` 工具通过 MCP 在容器内执行
   - Skills 目录只读挂载，执行环境与数据统一在 `/workspace`
3. **有状态 Python REPL**

   - `run_python_code` 在容器内执行，变量跨调用保留
4. **记忆压缩**

   - 保留最近 3 轮完整对话
   - 更早历史自动压缩为摘要
   - 保护已读取的 Skill 文档不被压缩
5. **计算 / 展示分离**

   - 技能输出结构化数据（JSON）
   - 展示由 `render_chart` / `render_table` / `show_notification` 完成

## CopilotKit 集成现状

 **已打通：**

- 后端 `/copilotkit/chat` SSE 通路已实现
- Agent 可产生客户端工具调用并由前端渲染

 **未打通（交互闭环）：**

- 前端未运行在 CopilotKit 标准 Runtime 中
- 当前使用自定义 SSE 协议解析
- 图表/表格点击等交互未回流为上下文或新一轮推理

 **原因简述：**

- 未启用 `CopilotKit` Provider
- 未使用 `useCopilotReadable` 等上下文同步能力
- UI 事件未接入 CopilotKit runtime 协议

## [COPILOTKIT-LOOP] 交互闭环预留

**目标**：图表/表格交互 → 前端上下文同步 → Agent 再推理 → 新 UI 输出**现状**：后端 Adapter 已可用，但前端仍使用自定义 SSE，未接入 CopilotKit 标准 Runtime。**保留后端逻辑的策略**：保留 `server/copilot_adapter.py`，只替换前端运行时与上下文同步方式。**最小改造路径**：

- 启用 `CopilotKit` Provider
- 使用 `useCopilotReadable` 写入交互状态
- 触发一次消息或自动再推理以形成闭环

## 快速开始

### 1) 安装依赖

```bash
 # Python 依赖
 pip install -r requirements-agent.txt
 
 # 前端依赖
 cd frontend
 npm install
```

### 2) 配置环境变量

```bash
 copy env.example .env  # Windows
 # 或
 cp env.example .env    # Linux/Mac
```

 在 `.env` 中设置：

```env
 DEEPSEEK_API_KEY=sk-xxxxxxxxxxxx
 # 可选：SANDBOX_IMAGE=claude-skills-sandbox:latest
```

### 3) 构建 Docker 沙盒镜像

```bash
 docker build -t claude-skills-sandbox:latest docker-sandbox
```

### 4) 运行方式

```bash
 # CLI 单次模式
 python -m agent_system.main "分析 showcase_financial_pl_data.csv"
 
 # 后端 API
 uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload
 
 # 前端开发
 cd frontend
 npm run dev
 
 # 一键联调（可选）
 python dev_server.py
```

## API 简述

- `POST /sessions`：创建会话
- `POST /sessions/{id}/files`：上传文件
- `POST /sessions/{id}/messages`：触发 Agent（子进程模式）
- `GET /sessions/{id}/stream`：SSE 日志流
- `GET /sessions/{id}/outputs`：查看输出文件
- `POST /copilotkit/chat`：CopilotKit Adapter SSE 通路

## 目录结构

```
 csv-data-summarizer/
 ├── agent_system/            # Agent 核心
 ├── docker-sandbox/          # MCP Server + Docker 镜像
 ├── server/                  # FastAPI + CopilotKit Adapter
 ├── frontend/                # React 前端（ChatLayout + Actions）
 ├── skills/                  # Skills 定义与参考代码
 ├── sessions/                # 会话数据（uploads/output/log）
 ├── tests/                   # 阶段性测试
 └── README.md
```

## 添加新技能

1. 新建目录：`skills/my-skill/`
2. 编写 `SKILL.md`（含 YAML frontmatter）
3. 可选：补充参考代码与 resources
4. 重启 Agent 即可自动索引元数据

 示例：

```markdown
 ---
 name: my-skill
 description: 我的技能说明
 ---
 
 # 使用说明
 1. 读取输入文件
 2. 执行计算
 3. 输出结构化 JSON
```

## 测试

```bash
 python tests/test_phase1_client_side_tools.py
 python tests/test_phase2_copilot_adapter.py
 python tests/test_phase4_skill_purification.py
```

## 已知限制

- CopilotKit 交互闭环尚未打通（见“集成现状”）
- Docker 必须可用（MCP 沙盒依赖）
- 沙盒默认无网络（`--network none`）
- Bash 工具有白名单限制（禁止管道/重定向/连接符）

## 参考资料

- Claude Skills 官方文档：https://code.claude.com/docs/en/skills
- MCP 协议：https://github.com/anthropics/mcp

---

 **建议用途**：用于内部复现 Claude Skills 架构、CopilotKit 端到端通路验证与技能机制实验。
