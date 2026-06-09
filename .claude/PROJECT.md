# 项目记忆

## 技术栈
- Python 项目，评估主链位于 `agent_system/evaluation/`
- 测试框架使用 `pytest`
- benchmark task 定义位于 `evaluations/tasks/*.json`

## 当前评估链路
- `BenchmarkRunner` 负责跑 task、收集 `run.json` / `trajectory.jsonl` / `artifacts.json`
- `RuleScorer` 负责 task-aware 打分
- `SkillComparator` 负责 `no_skill` vs `with_skill` 对比
- `ground_truth` 现在应作为答案真值源，`verifier` 负责描述 check 类型、path、tolerance、weight 等判分规则

## 开发约定
- Phase 2 结果验证改造采用 result-first：优先看最终回答，而不是 trajectory
- `final_response_text` 在 verifier 中必须按 JSON-only 严格解析，解析失败要显式失败，不能静默降级
- `task_success` 仍保留，但主判定要受 verifier/rubric 驱动
- `weighted_score` 允许保留过程分，但默认由 `result_score` 主导
- 新 task 优先写成“`ground_truth` 存值、`verifier` 不重复写 expected”；默认由 verifier 按 check.path 从 `ground_truth` 取 expected，特殊情况再用 `expected_from`

## 踩坑记录
- 旧链路只把 `final_response_present` 传给 scorer，没有把最终文本下传，导致无法做真正的结果校验
- 旧 comparator 只看 `avg_weighted_score`，会掩盖“结果错但过程像对”的情况
- 旧 task 的 `scoring_weights` 没有 `result_score` 字段，接入 verifier 时要做最小兼容，不能直接破坏已有结构
- `ground_truth` 和 `verifier.expected` 双写容易漂移；现已增加联动能力与一致性校验，后续不要再手工维护两份相同真值

## 本次范围
- 仅实现 `phase2-12` 第一版 verifier 执行层与 result-first 评分接入
- 优先保证 4 个 CSV task 可运行
- 不做 phase2-13/14，不引入 model judge，不重做 task 设计

## 后续待办
- 后续可补更多 verifier target / check 类型
- 后续可考虑把更多 finance task 迁移到结果校验
- 后续可补更细的 comparator 报表展示
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
- 运行记录：`sessions/{session_id}/runs/{run_id}/`
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
- 右侧标签：文件系统 / Skill / Trajectory / Evaluation

## 踩坑记录

- 仓库当前没有 `pyproject.toml`，不能直接走 `uv` 工作流
- `server/copilot_adapter.py` 会清理 `sessions/{id}/temp`
- `workspace/file` 当前只支持文本类文件预览，二进制文件会返回 `415`
- `llm_client.py` 的 `_meta` 字段是追加的，不影响 `core.py` 对已有字段的消费
- recorder 文件句柄在 `finalize()` 中关闭，异常路径也需确保关闭
- 评分失败不阻塞主流程，降级写入空分数
- 评估文档当前同时存在根目录和 `docs/Agent&Skills_Evals/` 副本，后续应以 `docs/Agent&Skills_Evals/` 为主，避免文档分叉
- 当前阶段不适合先做泛化 Agent Benchmark，`Phase 2` 主线已收敛为 `Skills Eval Harness + Skill Uplift / Routing Eval`

## Phase 1: Trajectory 与最小 Eval（已完成）

### 新增模块
- `agent_system/evaluation/` — 评估核心模块
  - `models.py`: 数据模型 (RunRecord, TrajectoryEvent, EvalRecord, ArtifactsRecord, RunIndexEntry)
  - `recorder.py`: 运行记录器，管理 trajectory.jsonl 实时追加和 run 落盘
  - `scorer.py`: 规则评分器 (task_success, tool_efficiency, artifact_completeness, trajectory_quality)
  - `registry.py`: runs_index.json 跨会话索引维护 + 本地任务匹配
- `evaluations/` — 评估数据目录
  - `runs_index.json`: 跨会话 run 索引
  - `tasks/*.json`: 本地任务定义（csv_analysis_basic, skill_explanation）

### 数据落盘结构
```
sessions/{session_id}/runs/{run_id}/
  run.json          — 运行主元数据
  trajectory.jsonl  — 结构化事件流
  eval.json         — 规则评分结果
  artifacts.json    — 产物文件列表
```

### 后端接口
- `GET /sessions/{sid}/runs` — 会话 run 列表
- `GET /sessions/{sid}/runs/{rid}` — run 详情
- `GET /sessions/{sid}/runs/{rid}/trajectory` — 轨迹事件
- `GET /sessions/{sid}/runs/{rid}/eval` — 评估结果
- `GET /evaluation/runs` — 跨会话 run 索引
- `GET /evaluation/tasks` — 本地任务定义

### SSE 增强
- `done` 事件现在附带 `run_id`，前端可自动刷新 run 数据

### 前端变更
- 右侧标签调整为：文件系统 / Skill / Trajectory / Evaluation
- `TrajectoryPanel`: 运行摘要卡片 + 评分条 + 时间线
- `EvaluationPanel`: 会话 run 列表 + 全局 run 列表 + delta 对比
- `ChatLayout` 增加 activeRunId / 自动拉取 run 详情逻辑

## 后续待办

- `Phase 2` 规划文档：`docs/phase2-benchmark-skill-eval-plan.md`
- `Phase 2` 核心目标：以 `Skills Eval` 为主线，先做本地薄 harness，再做 `Phase A/B/C`
- `Phase 2` 主文档归档：`docs/Agent&Skills_Evals/phase2-benchmark-skill-eval-plan.md`
- `Skills Eval Harness` 设计稿：`docs/Agent&Skills_Evals/skills-eval-harness-minimal-design.md`
- `Phase 2` 代码阶段入口：`docs/Agent&Skills_Evals/implementation-plan.md`
- `Phase 2` 当前主问题已从“runner 是否跑通”转为“scorer 是否真正评估结果”；下一阶段优先做 verifier / rubric（`phase2-12`）
- `Phase A`：`Skills Uplift Eval`，优先支持 `no_skill / with_skill / skill_v1 / skill_v2`
- `Phase B`：`Skill Routing / Integration Eval`，补 `activation precision / recall / F1`
- `Phase C`：外部平台接入与更薄的 Base Agent Eval，放在本地 harness 跑通之后
- `Phase 2` 仍然坚持本地事实源，不接外部 eval 平台
- 联网能力规划文档：`docs/web-search-tool-design.md`
- 联网能力当前路线：先做 provider-neutral 的 `WebSearch`，底层接 `Tavily`，后续再按真实场景补 `WebExtract`
- 联网工具命名与返回结构不直接透传 provider 原生 schema，
优先保持 Agent 能力语义稳定
- 为 `workspace` 接口补测试
- 为中间文件查看器补 JSON/日志专用增强视图
- 接入 CopilotKit 标准 Runtime

