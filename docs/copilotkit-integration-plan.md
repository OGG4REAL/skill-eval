 # CopilotKit 集成计划：DeepSeek 风格 Chatbot & Generative UI (Sidecar 模式)
 
 ## 🎯 核心目标
 将现有的 "CSV Data Summarizer" 升级为**工具驱动的对话式 AI 助手**。
 采用 **In-Process Adapter (Sidecar)** 模式，保持 CopilotKit 原生体验，同时复用现有 Agent 的强大能力。
 
 1.  **Agent 核心保留**：保留 `agent_system` 的 Python 循环、Docker 沙箱和 Skill 机制。
 2.  **CopilotKit 接管交互**：前端使用 CopilotKit 实现流式对话、思考过程展示 (Thinking Process) 和 Generative UI。
 3.  **客户端工具适配 (Client-Side Tools)**：修改 Agent Core 以识别 `client_side=True` 的工具，将 UI 渲染指令无缝传递给前端，实现"计算"（后端）与"展示"（前端）的解耦。
 4.  **上下文融合**：利用 `useCopilotReadable` 将前端状态（表格选中、页面数据）实时同步给 Agent。
 
 ---
 
 ## 🏗 架构设计 (Architecture)
 
 ### 1. 运行时架构 (In-Process Execution)
 *   **旧模式**：每次请求启动子进程 (`subprocess.Popen`)。
 *   **新模式**：**进程内异步执行**。FastAPI (Adapter) 维护一个 `Agent` 实例池。请求到来时，利用 `asyncio.to_thread` 在线程池中运行同步的 `agent.run()`，避免阻塞主线程，同时大幅降低延迟。
 
 ### 2. 数据流闭环 (The Loop)
 
 1.  **用户提问 (Frontend)**
     *   CopilotKit SDK 捕获用户输入和 `useCopilotReadable` 上下文。
     *   发送请求到后端 `/copilotkit` 端点。
 
 2.  **适配层 (Adapter Middleware)**
     *   位于 `server/copilot_adapter.py`。
     *   **上下文注入**：将前端 Context 注入 Agent 的 System Prompt。
     *   **思考流 (Thinking Stream)**：注册回调函数，将 Agent 的 `rich` 日志实时转换为 CopilotKit 的流式消息（展示为"正在思考..."）。
 
 3.  **大脑思考 (Agent System)**
     *   Agent 分析问题，调用 Skill（如 `fin-advisor-math`）进行纯数据计算。
     *   **UI 决策**：Agent 决定展示图表，调用全局工具 `render_chart`。
 
 4.  **客户端工具拦截 (Client-Side Interception)**
     *   **Agent Core 修改**：Agent 检测到 `render_chart` 标记为 `client_side=True`。
     *   **跳过执行**：Python 端不执行任何逻辑，直接生成特殊指令返回给 Adapter。
     *   **协议转换**：Adapter 将此指令转换为 CopilotKit 标准 `toolCall`。
 
 5.  **渲染反馈 (Frontend)**
     *   前端收到 Tool Call，触发 `renderFinancialChart` Action。
     *   Generative UI 组件在对话流中渲染图表。
 
 ---
 
 ## 📅 实施路线图 (Roadmap)
 
 我们分四个阶段进行，确保每一步都是可测试的。
 
 ### Phase 1: Agent Core 升级 (Client-Side Tools & Async Support) ✅ 已完成
 
 **目标**：让 Agent 能够"识别"前端工具，并支持流式日志回调。
 
 #### 实现内容
 
 1.  **修改 `agent_system/tools/base.py`**：
     *   新增 `ClientSideToolResult` 数据类，用于封装客户端工具调用结果
     *   在 `BaseTool` 基类中添加 `client_side = False` 属性
 
 2.  **修改 `agent_system/agent/core.py`**：
     *   `Agent.run()` 新增 `callback: LogCallback` 参数，支持实时日志回调
     *   返回值从 `str` 改为结构化 `Dict`：
         ```python
         {
             "response": str,           # 最终回复文本
             "client_side_tools": list, # 客户端工具调用列表
             "iterations": int          # 实际迭代次数
         }
         ```
     *   工具执行循环中检测 `tool.client_side` 属性，若为 `True` 则：
         - 跳过 `tool.execute()` 调用
         - 创建 `ClientSideToolResult` 加入收集器
         - 返回占位消息给 LLM 继续对话
 
 3.  **创建 `agent_system/tools/ui_tools.py`**：
     *   实现 3 个客户端工具（均标记 `client_side=True`）：
 
     | 工具名 | 功能 | 关键参数 |
     |--------|------|----------|
     | `render_chart` | 渲染图表 | `title`, `chart_type`(7种), `data`, `options` |
     | `render_table` | 渲染表格 | `title`, `columns`, `rows`, `options` |
     | `show_notification` | 显示通知 | `message`, `type`, `duration` |
 
 4.  **更新 `agent_system/main.py`**：
     *   启动时自动注册 UI 工具
     *   适配新的返回值结构
 
 #### 测试验证
 
 测试文件：`tests/test_phase1_client_side_tools.py`
 
 ```bash
 python tests/test_phase1_client_side_tools.py
 # 6 测试全部通过
 ```
 
 ---
 
 ### Phase 2: 后端适配器 (The Sidecar) ✅ 已完成
 **目标**：建立 CopilotKit 与 Agent 之间的桥梁。
 
 1.  **依赖安装**：
     ```bash
     pip install copilotkit
     ```
 
 2.  **创建 `server/copilot_adapter.py`**：
     *   实现 `CopilotBackend` 类。
     *   维护 `session_id -> Agent` 的实例缓存。
     *   实现 `stream` 接口：
         *   启动 `agent.run()` (in thread)。
         *   监听 Agent 回调，推送 "Thinking" 日志。
         *   捕获 Agent 最终回复，推送 Text Message。
         *   捕获 `client_side` 工具调用，推送 Tool Call。
 
 3.  **挂载路由**：
     *   在 `server/app.py` 中挂载 `/copilotkit` 路由。
 
 #### 🔧 协议规范 (Protocol Spec)
 *   **Request**: POST `/copilotkit/chat`
     ```json
     {
       "messages": [...],
       "frontend": { "url": "...", "context": {...} },
       ...
     }
     ```
 *   **Response (SSE)**:
     *   `event: text` -> data: "正在思考..." (Log stream)
     *   `event: text` -> data: "分析结果如下..." (Final Answer)
     *   `event: tool_call` -> data: { name: "render_chart", args: ... } (Client-side Tools)
 
 #### 🛡 异常处理
 *   **Agent Crash**: 若 Agent 线程抛出异常，捕获并发送 `event: error`，避免前端无限等待。
 *   **Timeout**: 设置 60s 硬超时，超时后发送友好提示。
 
 #### 🛠 调试工具
 *   新增 `GET /copilotkit/debug`: 查看活跃 Session 列表和内存占用。
 
 #### ⚠️ 技术注意事项
 
 *   **回调线程安全**：`callback` 会在 `asyncio.to_thread` 的线程池中被调用，需确保推送到 SSE 流时使用 `asyncio.run_coroutine_threadsafe()` 或队列机制。
 *   **Agent 实例管理**：
     - 建议使用 LRU 缓存管理 Agent 实例（按 session_id）
     - 设置合理的过期时间（如 30 分钟无活动自动释放）
     - 注意 Docker 容器的生命周期与 Agent 实例绑定
 *   **CopilotKit 协议**：需研究 `@copilotkit/runtime` 的消息格式，确保 `client_side_tools` 能正确转换为 CopilotKit 的 `toolCall` 事件。
 
 ---
 
 ### Phase 3: 前端重构 (DeepSeek UI) ✅ 已完成
 **目标**：建立支持流式对话和 GenUI 的外壳。
 
 #### 实现内容
 
 1.  **安装 CopilotKit 依赖**：
     ```bash
     npm install @copilotkit/react-core @copilotkit/react-ui @copilotkit/react-textarea lucide-react clsx tailwind-merge react-markdown remark-gfm
     ```
 
 2.  **配置 Vite 代理**（`vite.config.ts`）：
     - `/copilotkit` -> `http://localhost:8000`
     - `/sessions` -> `http://localhost:8000`
 
 3.  **创建 CopilotKit 模块**（`src/copilot/`）：
 
     | 文件 | 功能 |
     |------|------|
     | `CopilotProvider.tsx` | CopilotKit 上下文 Provider |
     | `ChatLayout.tsx` | DeepSeek 风格全屏对话布局 |
     | `types.ts` | TypeScript 类型定义 |
     | `components/ThinkingPanel.tsx` | 折叠式思考过程面板 |
     | `components/MarkdownRenderer.tsx` | Markdown 渲染组件 |
     | `actions/ChartAction.tsx` | ECharts 图表渲染 |
     | `actions/TableAction.tsx` | 交互式表格渲染 |
     | `actions/NotificationAction.tsx` | 通知提示渲染 |
 
 4.  **注册 useCopilotAction**：
     - `render_chart` -> ChartAction (支持 7 种图表类型)
     - `render_table` -> TableAction (支持排序、分页)
     - `show_notification` -> NotificationAction (支持 4 种类型)
 
 5.  **入口切换**（`main.tsx`）：
     - 默认使用新版 `CopilotApp`
     - `?mode=legacy` 可切换回旧版 App
 
 #### 功能亮点
 
 - 🎨 **DeepSeek 风格 UI**：深色主题，渐变配色，毛玻璃效果
 - 💭 **思考过程展示**：折叠式面板显示 Agent 思考步骤
 - 📊 **Generative UI**：图表/表格/通知在对话流中内联渲染
 - 🔄 **流式响应**：SSE 协议实时显示思考过程
 - 📝 **Markdown 支持**：完整的 GFM 语法支持
 
 #### 使用方式
 
 ```bash
 # 启动前端开发服务器
 cd frontend && npm run dev
 
 # 访问新版 CopilotKit UI
 http://localhost:5173/
 
 # 访问旧版 UI（兼容模式）
 http://localhost:5173/?mode=legacy
 ```
 
 #### 技术实现细节
 
 *   **图表数据转换**：`ChartAction.tsx` 中的 `convertToEChartsOption()` 负责将后端格式转换为 ECharts 配置
     ```typescript
     // 后端格式
     { labels: ["Q1", "Q2"], datasets: [{ name: "销售", values: [100, 200] }] }
     // 转换为 ECharts 格式
     { xAxis: { data: ["Q1", "Q2"] }, series: [{ name: "销售", data: [100, 200] }] }
     ```
 
 *   **SSE 事件解析**：`ChatLayout.tsx` 解析后端返回的 SSE 事件流
     - `type: thinking` -> 添加到思考步骤
     - `type: tool_call` -> 显示工具调用
     - `type: response` -> 最终回复
     - `name: render_chart` -> 触发图表渲染
 
 *   **Session 持久化**：通过 URL 参数或 localStorage 保持会话 ID
 
 ---
 
 ### Phase 4: Skill 净化 & 全局能力 ✅ 已完成
 **目标**：解耦计算与展示，确立 Orchestrator 的 UI 控制权。
 
 #### 实现内容
 
 1.  **Prompt 增强 (`prompts.py`)**：
     *   新增 `<client_side_ui_tools>` 部分，包含：
         - 所有 UI 工具列表（render_chart, render_table, show_notification）
         - UI 决策规则表（何时使用何种图表类型）
         - 禁止使用 matplotlib/seaborn 的明确指令
         - Orchestrator 负责展示的职责声明
 
 2.  **Skill 净化 - `fin-advisor-math/SKILL.md`**：
     *   移除"复杂场景"中手动构建 JSON 图表数据的代码示例
     *   将输出改为纯计算结果（结构化 JSON）
     *   新增"可视化规则"部分，明确声明：
         - "此 Skill 仅负责计算，不负责展示"
         - 禁止使用 matplotlib/seaborn/plt.savefig()
         - 引导使用 Orchestrator 的 render_chart/render_table
 
 3.  **Skill 净化 - `csv-data-summarizer/SKILL.md`**：
     *   版本升级：4.0.0 → 5.0.0
     *   移除 `ANALYSIS_RESULT_START/END` 协议（标记为 deprecated）
     *   移除 JSON 输出中的 `charts` 数组配置
     *   新增 `data` 结构用于输出计算结果
     *   更新头部声明："COMPUTATION ONLY - VISUALIZATION IS HANDLED BY ORCHESTRATOR"
     *   新增"Visualization Guidelines"部分，说明 Orchestrator 如何使用输出数据
 
 #### 测试验证
 
 测试文件：`tests/test_phase4_skill_purification.py`
 
 ```bash
 python tests/test_phase4_skill_purification.py
 # 19 测试全部通过
 ```
 
 测试覆盖：
 - `TestPromptsUIDecisionRule`: 验证 prompts.py 中 UI 工具决策规则
 - `TestFinAdvisorMathSkillPurification`: 验证金融计算技能净化
 - `TestCSVDataSummarizerSkillPurification`: 验证 CSV 分析技能净化
 - `TestUIToolsIntegration`: 验证 UI 工具集成
 
 #### ⚠️ 技术注意事项
 
 *   **双重输出防护**：
     - 当 Agent 调用了 `render_chart` 后，可能仍会在回复中描述图表内容
     - 前端需智能处理，避免"图表 + 图表描述文字"的冗余
 *   **Skill 回退机制**：
     - 如果前端不支持 Generative UI（如 CLI 模式），Agent 应检测环境并回退到生成 matplotlib 代码（可选高级特性）
 
 ---
 
 ## 🛡 风险管理
 
 *   **超时问题**：Agent 思考时间可能较长（>30s）。需确保前端和 Nginx/代理层配置了足够的超时时间，且流式连接（SSE）保持心跳。
 *   **状态同步**：Agent 是有状态的（Python 变量），前端刷新页面后 Session ID 需保持一致，否则上下文会丢失。建议将 Session ID 存储在 URL 或 LocalStorage 中。
 *   **Docker 容器泄漏**：Agent 实例管理不当可能导致 Docker 容器未被清理。建议：
     - 在 Agent 缓存过期时主动调用 `mcp_client.cleanup()`
     - 设置容器的 `--rm` 标志
     - 定期运行 `docker container prune` 清理僵尸容器
 
 ---
 
 ## 📁 文件变更清单 (Phase 1)
 
 ```
 agent_system/
 ├── tools/
 │   ├── base.py          # [修改] 新增 ClientSideToolResult, BaseTool.client_side
 │   ├── ui_tools.py      # [新增] RenderChartTool, RenderTableTool, ShowNotificationTool
 │   └── __init__.py      # [修改] 导出新增类
 ├── agent/
 │   └── core.py          # [修改] run() 返回结构、callback 参数、客户端工具检测
 └── main.py              # [修改] 注册 UI 工具、适配返回值
 
 tests/
 └── test_phase1_client_side_tools.py  # [新增] Phase 1 验证测试
 ```
 
 ## 📁 文件变更清单 (Phase 2)
 
 ```
 server/
 ├── copilot_adapter.py   # [新增] CopilotBackend 类、SSE 流、Agent 缓存池
 ├── app.py               # [修改] 挂载 /copilotkit 路由
 └── __init__.py          # [修改] 导出适配器类
 
 agent_system/tools/
 ├── mcp_tools.py         # [修改] 新增 create_mcp_tools() 工厂函数
 └── __init__.py          # [修改] 导出 MCP 工具类
 
 requirements-agent.txt   # [修改] 添加 copilotkit, cachetools 依赖
 
 tests/
 └── test_phase2_copilot_adapter.py  # [新增] Phase 2 验证测试 (10 个测试)
 ```
 
 ## 📁 文件变更清单 (Phase 3)
 
 ```
 frontend/
 ├── vite.config.ts           # [修改] 添加 /copilotkit 和 /sessions 代理
 ├── package.json             # [修改] 新增 CopilotKit 相关依赖
 ├── src/
 │   ├── main.tsx             # [修改] 支持 mode 参数切换新旧 UI
 │   ├── CopilotApp.tsx       # [新增] 新版入口组件
 │   └── copilot/
 │       ├── index.ts         # [新增] 模块导出
 │       ├── types.ts         # [新增] TypeScript 类型定义
 │       ├── CopilotProvider.tsx    # [新增] CopilotKit Provider
 │       ├── ChatLayout.tsx         # [新增] DeepSeek 风格对话布局
 │       ├── components/
 │       │   ├── index.ts           # [新增] 组件导出
 │       │   ├── ThinkingPanel.tsx  # [新增] 思考过程面板
 │       │   └── MarkdownRenderer.tsx # [新增] Markdown 渲染器
 │       └── actions/
 │           ├── index.ts           # [新增] Actions 导出
 │           ├── ChartAction.tsx    # [新增] 图表渲染 Action
 │           ├── TableAction.tsx    # [新增] 表格渲染 Action
 │           └── NotificationAction.tsx # [新增] 通知渲染 Action
 ```
 
 ## 📁 文件变更清单 (Phase 4)
 
 ```
 agent_system/agent/
 └── prompts.py           # [修改] 新增 <client_side_ui_tools> 部分，包含 UI 决策规则
 
 skills/
 ├── fin-advisor-math/
 │   └── SKILL.md         # [修改] 移除图表 JSON 构建代码，新增"可视化规则"部分
 └── csv-data-summarizer/
     └── SKILL.md         # [修改] v5.0.0，移除 ANALYSIS_RESULT 协议，新增 data 结构和 Visualization Guidelines
 
 tests/
 └── test_phase4_skill_purification.py  # [新增] Phase 4 验证测试 (19 个测试)
 ```
 
 ---
 
 ## ✅ 全部完成
 
 所有四个阶段均已实现：
 1. **Phase 1**: Agent Core 升级 - 支持客户端工具识别
 2. **Phase 2**: 后端适配器 - CopilotKit 与 Agent 的桥梁
 3. **Phase 3**: 前端重构 - DeepSeek 风格 UI 与 Generative UI
 4. **Phase 4**: Skill 净化 - 解耦计算与展示
 
 ## 🔜 下一步行动
 
 1. **E2E 测试**：启动后端和前端，验证完整的对话流程
 2. **样式优化**：根据实际效果微调 UI 细节
 3. **性能优化**：监控 Agent 响应时间，优化关键路径
