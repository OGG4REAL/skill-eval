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
