# PROJECT

## 技术栈

- 后端：`FastAPI`，入口在 `server/app.py`
- Agent：`agent_system/`，会话目录由 `agent_system/session.py` 管理
- 前端：`React 19 + Vite + TypeScript`，Copilot UI 入口在 `frontend/src/copilot/ChatLayout.tsx`
- Markdown 渲染：`react-markdown + remark-gfm`

## 会话目录约定

- 会话根目录：`sessions/{session_id}`
- 上传文件：`sessions/{session_id}/uploads`
- 输出文件：`sessions/{session_id}/output`
- 对话日志：`sessions/{session_id}/chat.log`
- 临时脚本：`sessions/{session_id}/temp`
- 工具落盘结果：`sessions/{session_id}/.tool-results`
- 历史摘要：`sessions/{session_id}/history.json`
- Skills 根目录：仓库 `skills/`，逻辑上挂载为 `/workspace/skills`

## Workspace 接口契约

后端在 `server/app.py` 提供：

- `GET /sessions/{session_id}/workspace`
- `GET /sessions/{session_id}/workspace/file?path=/workspace/...`

接口语义：

- 前端只使用逻辑路径 `/workspace/...`
- 不暴露真实物理路径
- `skills/` 标记为只读
- `.tool-results` 必须显示，不能按隐藏目录过滤
- 文件读取默认返回全文，不做摘要替代

## 前端实现约定

- `ChatLayout.tsx` 管理中间区模式切换：`chat` / `file`
- `WorkspacePanel.tsx` 负责右侧树、标签、即时预览
- `FileViewer.tsx` 负责中间大视图
- `WorkspaceResizeHandle.tsx` 负责右侧拖拽调宽
- `workspace` 宽度与开关状态持久化到 `localStorage`

## 本轮踩坑记录

- 仓库当前没有 `pyproject.toml`，不能直接走 `uv` 工作流
- `frontend` 的 `build` / `lint` 会被仓库既有问题挡住，当前已知包括：
  - `frontend/vite.config.ts` 存在未使用参数
  - `frontend/src/App.tsx`、`frontend/src/CopilotApp.tsx`、`frontend/src/components/ChartRenderer.tsx`、`frontend/src/copilot/components/ThinkingPanel.tsx` 有既有 lint 问题
- `server/copilot_adapter.py` 会清理 `sessions/{id}/temp`，所以 `Workspace` 里 `temp/` 需要按逻辑节点稳定展示，即使真实目录暂时为空或不存在
- `workspace/file` 当前只支持文本类文件预览，二进制文件会返回 `415`

## 后续待办

- 为 `workspace` 接口补测试，至少覆盖：
  - 路径越界拦截
  - `.tool-results` 展示
  - `skills/` 只读标记
  - `history.json` / `chat.log` / `SKILL.md` 读取
- 为中间文件查看器补 JSON/日志专用增强视图
- 优化长文件渲染性能，但不能改变“默认全文可见”的语义
 # 项目记忆（Claude Skills 复现）
 
 ## 技术栈
 - 后端：Python（FastAPI、Rich、Pydantic）
 - Agent：自研 Orchestrator + MCP Docker 沙盒
 - 前端：React + Vite + CopilotKit 组件
 - 可视化：ECharts（前端渲染）
 
 ## 关键依赖
 - `openai`（OpenAI 兼容接口，当前用于 DeepSeek）
 - `fastapi` / `uvicorn`
 - `copilotkit` / `cachetools`
 - Docker 镜像：`claude-skills-sandbox:latest`
 
 ## 运行入口
 - CLI：`python -m agent_system.main "..."`
 - API：`uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload`
 - 前端：`cd frontend && npm run dev`
 - 一键联调：`python dev_server.py`
 
 ## 开发约定
 - Skills 只加载元数据；完整内容由 Agent 通过 `bash("cat skills/.../SKILL.md")` 自主读取
 - 技能只负责计算，展示由客户端 UI 工具完成
 - MCP 工具仅允许白名单命令（无管道/重定向/连接符）
 
 ## 踩坑记录
 - CopilotKit 交互闭环未打通：前端未启用 CopilotKit 标准 Runtime（未使用 Provider/hooks，使用自定义 SSE）
 - 技能输出协议已去掉 `ANALYSIS_RESULT_START/END`，不要再依赖旧前端解析逻辑
 
 ## 待办
- 引入 Skill 工具与两阶段注入（Phase1 文档已记录）
- Phase2：精简 system prompt，工具规则下沉到 description
 - 接入 CopilotKit 标准 Runtime（`CopilotKit` Provider + `useCopilotReadable`）
 - 完善图表点击/选择等交互事件的上下文回流
