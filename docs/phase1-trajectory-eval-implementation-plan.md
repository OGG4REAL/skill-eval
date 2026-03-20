# Phase 1 实施规划：Trajectory 与最小 Eval

## 1. 文档定位

这是一份给实现者直接使用的 `Phase 1` 规划与技术文档。  
目标不是继续讨论“要不要做评估”，而是明确：

- `Phase 1` 到底做什么
- 哪些能力必须落地
- 哪些能力明确延期
- 后端、前端、数据层分别怎么拆
- 最终验收标准是什么

本文默认读者已经看过：

- `docs/agent-evaluation-trajectory-design.md`
- `docs/agent-workspace-rebuild-plan.md`

如果没有看过，也可以直接按本文实施。

## 2. Phase 1 结论先行

### 2.1 本阶段的明确目标

`Phase 1` 要解决的是：

1. 单次运行可回放
2. 多次运行可比较
3. 评估数据有本地事实源
4. UI 中能直接看到 trajectory 和最小 eval

### 2.2 本阶段明确不做

`Phase 1` 明确不做：

- 不接 `LangSmith`
- 不接 `Langfuse`
- 不做外部 trace 同步
- 不做 `LLM-as-a-Judge`
- 不做完整 skill benchmark matrix
- 不做复杂在线评估平台
- 不做通用化的评测 DSL

### 2.3 Phase 1 的核心交付

必须交付：

- 本地 `run` 数据
- 本地 `trajectory` 数据
- 本地 `eval` 数据
- 本地 `runs_index`
- Workspace 内新增 `Trajectory` / `Evaluation` 视图
- 最小规则评分能力

## 3. 需求镜像

### 3.1 业务目标

当前 `Agent Studio` 已经具备：

- 会话目录
- workspace 浏览
- 长文件查看
- thinking / tool 调用展示

但仍缺少：

- 一次运行的结构化轨迹
- 多次运行的自动比较
- 对 skill 增益的基础验证手段

所以 `Phase 1` 的本质不是“上评测平台”，而是：

**先把本地评估事实层补起来。**

### 3.2 用户画像

本文面向三类使用者：

1. 产品演示者
   - 想解释 Agent 刚才做了什么
2. 开发者
   - 想定位哪一步慢、哪一步错、哪一步多余
3. 调优者
   - 想比较优化前后是否真的有提升

## 4. 范围定义

### 4.1 In Scope

本阶段在范围内：

- 为每次任务执行生成唯一 `run_id`
- 为每次运行落盘结构化轨迹
- 为每次运行生成最小评估结果
- 提供会话级 run 列表查询接口
- 提供 run 详情 / trajectory / eval 查询接口
- 在前端右侧区域引入 `Trajectory` / `Evaluation`
- 支持查看最近若干次运行并进行轻量对比
- 为后续引入 skill benchmark 预留字段

### 4.2 Out of Scope

本阶段不在范围内：

- benchmark runner CLI
- 批量回放任务集
- 自动数据集管理平台
- 云端 experiment 对比
- LLM judge
- 人工标注工作流
- 全局平台级 dashboard
- token / cost 的精准财务归因

## 5. 当前系统切入点

## 5.1 后端现状

当前后端已有：

- `server/app.py`
  - workspace 树与文件读取接口
- `server/copilot_adapter.py`
  - SSE 流式事件桥接
- `agent_system/agent/core.py`
  - 真正的 agent 执行主循环
- `agent_system/agent/llm_client.py`
  - 模型调用封装

现有运行时已经产生这些过程信号：

- `thinking`
- `tool_call`
- `tool_result`
- `client_side_tool`
- `error`

但这些目前：

- 只部分进入前端流式展示
- 没有结构化持久化
- 无法形成可比较 run

### 5.2 前端现状

当前前端已有：

- `ChatLayout.tsx`
  - 聊天主布局
- `WorkspacePanel.tsx`
  - 右侧文件树与预览
- `ThinkingPanel.tsx`
  - 展示流式过程步骤

当前问题：

- `ThinkingPanel` 更像“当前消息的流式附属视图”
- 缺乏“本次运行”的统一摘要与时间线
- 缺乏“历史运行”的列表和差异比较

## 6. 信息架构决策

### 6.1 Workspace 标签调整

建议在 `Phase 1` 中对右侧标签做收口：

当前：

- `工件`
- `文件系统`
- `Skill`
- `调试`

建议调整为：

- `文件系统`
- `Skill`
- `Trajectory`
- `Evaluation`

原因：

- `工件` 当前价值偏低，因为产物主要在前端直接渲染或容器内执行完成
- `调试` 的语义过弱，无法承载“运行轨迹 + 比较”的目标
- `Trajectory` 更准确表达“本次运行过程”
- `Evaluation` 更准确表达“跨 run 比较”

### 6.2 中间区不做大改

`Phase 1` 不建议重构中间主区域。

中间区继续保留：

- 对话
- thinking
- 文件查看器

评估相关能力先放在右侧：

- `Trajectory`
- `Evaluation`

这样可以把改动范围控制在最小可用层。

## 7. 数据模型

### 7.1 目录结构

建议新增如下结构：

```text
sessions/{session_id}/
  runs/
    {run_id}/
      run.json
      trajectory.jsonl
      eval.json
      artifacts.json

evaluations/
  runs_index.json
  tasks/
    csv_analysis_basic.json
    skill_explanation.json
```

说明：

- `sessions/{session_id}/runs/{run_id}` 保存单次运行事实
- `evaluations/runs_index.json` 保存跨会话索引
- `evaluations/tasks/*.json` 保存本地任务定义

### 7.2 run.json

用途：

- 本次运行的主元数据

建议结构：

```json
{
  "run_id": "run_20260319_102000_ab12cd",
  "session_id": "8849126355554f098cad546d60256a6e",
  "task_id": "adhoc",
  "variant_id": "baseline",
  "skills": ["csv-data-summarizer"],
  "trigger": "chat",
  "user_input": "分析我上传的 csv",
  "started_at": "2026-03-19T10:20:00Z",
  "finished_at": "2026-03-19T10:20:18Z",
  "duration_ms": 18342,
  "status": "passed",
  "iterations": 4,
  "tool_calls": 7,
  "tool_errors": 0
}
```

字段要求：

- `task_id`
  - `Phase 1` 默认支持 `adhoc`
  - 若命中本地任务定义，可写入明确任务 ID
- `variant_id`
  - 默认 `baseline`
- `skills`
  - 记录本次实际注入或使用的 skill

### 7.3 trajectory.jsonl

用途：

- 保存一步一步的结构化运行轨迹

格式：

- JSONL，一行一个事件

建议事件类型：

- `run_started`
- `iteration_started`
- `llm_call_started`
- `llm_call_finished`
- `thinking`
- `tool_call_started`
- `tool_call_finished`
- `tool_result_recorded`
- `client_tool_emitted`
- `skill_injected`
- `artifact_created`
- `run_completed`
- `run_failed`

示例：

```json
{"type":"run_started","run_id":"run_001","timestamp":"2026-03-19T10:20:00Z"}
{"type":"iteration_started","run_id":"run_001","step_index":1,"iteration":1,"timestamp":"2026-03-19T10:20:00Z"}
{"type":"thinking","run_id":"run_001","step_index":2,"iteration":1,"message":"第 1 轮思考...","timestamp":"2026-03-19T10:20:00Z"}
{"type":"tool_call_started","run_id":"run_001","step_index":3,"iteration":1,"tool_name":"Read","arguments":{"path":"/workspace/uploads/test.csv"},"timestamp":"2026-03-19T10:20:01Z"}
{"type":"tool_call_finished","run_id":"run_001","step_index":4,"iteration":1,"tool_name":"Read","status":"success","duration_ms":12,"timestamp":"2026-03-19T10:20:01Z"}
{"type":"artifact_created","run_id":"run_001","step_index":5,"path":"/workspace/temp/analysis_001.py","timestamp":"2026-03-19T10:20:02Z"}
{"type":"run_completed","run_id":"run_001","timestamp":"2026-03-19T10:20:18Z","status":"passed"}
```

### 7.4 eval.json

用途：

- 保存单次运行的最小评估结果

建议结构：

```json
{
  "run_id": "run_001",
  "task_id": "adhoc",
  "variant_id": "baseline",
  "status": "passed",
  "metrics": {
    "duration_ms": 18342,
    "iterations": 4,
    "tool_calls": 7,
    "tool_errors": 0,
    "files_generated": 2
  },
  "scores": {
    "task_success": 1,
    "tool_efficiency": 0.86,
    "artifact_completeness": 0.5,
    "trajectory_quality": 0.78
  },
  "notes": []
}
```

### 7.5 artifacts.json

用途：

- 汇总本次运行涉及的关键文件，便于前端快捷跳转

建议结构：

```json
{
  "run_id": "run_001",
  "files": [
    "/workspace/chat.log",
    "/workspace/history.json",
    "/workspace/temp/analysis_001.py",
    "/workspace/.tool-results/call_xxx.txt"
  ]
}
```

### 7.6 runs_index.json

用途：

- 跨会话聚合最近运行
- 支撑 Evaluation 面板

建议结构：

```json
[
  {
    "run_id": "run_001",
    "session_id": "8849126355554f098cad546d60256a6e",
    "task_id": "adhoc",
    "variant_id": "baseline",
    "skills": ["csv-data-summarizer"],
    "status": "passed",
    "score": 0.79,
    "duration_ms": 18342,
    "tool_calls": 7,
    "created_at": "2026-03-19T10:20:18Z"
  }
]
```

## 8. 规则评分设计

### 8.1 第一版分数项

只做 4 个分数：

1. `task_success`
2. `tool_efficiency`
3. `artifact_completeness`
4. `trajectory_quality`

### 8.2 评分建议

#### A. task_success

规则：

- 最终无报错且有非空最终回复 -> `1`
- 否则 -> `0`

#### B. tool_efficiency

基础启发式：

- 失败工具调用越多，分越低
- 工具数明显超出迭代规模，分越低
- 没有失败且工具总数适中，分数较高

示意规则：

```text
base = 1.0
- 0.15 * tool_errors
- 0.05 * extra_tool_calls
最小为 0
```

#### C. artifact_completeness

规则：

- 若存在预期文件定义，则按命中率给分
- 若任务无产物要求，则设为 `null` 或 `1`

`Phase 1` 对 `adhoc` 可采用：

- 如果产生了任何 `temp/`、`.tool-results/`、`output/` 产物则给较高分
- 无产物但也不强制要求时，允许为 `null`

#### D. trajectory_quality

第一版不做 LLM judge。  
用启发式近似：

- 无失败
- 轮数不过多
- 工具路径无明显失控
- 结束状态正常

## 9. 任务定义

### 9.1 Phase 1 为什么还要有 tasks

即使 `Phase 1` 不做完整 benchmark，也建议预埋本地任务定义能力。

原因：

- 让后续 `Phase 2` 平滑进入 task benchmark
- 为规则评分保留明确预期

### 9.2 Phase 1 任务定义最小结构

建议目录：

- `evaluations/tasks/*.json`

示例：

```json
{
  "task_id": "csv_analysis_basic",
  "input_patterns": ["分析我上传的 csv", "分析这个 csv"],
  "expected_signals": [
    "tool:Read:/workspace/uploads/",
    "client_tool:render_chart|render_table"
  ],
  "expected_artifacts": [],
  "pass_criteria": {
    "final_response_non_empty": true,
    "tool_errors_max": 0
  }
}
```

### 9.3 Phase 1 如何使用 tasks

`Phase 1` 不做复杂路由器。  
只需要：

- 如果用户输入能匹配本地任务定义，则写入对应 `task_id`
- 否则一律写为 `adhoc`

## 10. 后端实施方案

### 10.1 代码组织建议

建议新增模块：

```text
agent_system/evaluation/
  __init__.py
  models.py
  recorder.py
  scorer.py
  registry.py
```

职责建议：

- `models.py`
  - `RunRecord`
  - `TrajectoryEvent`
  - `EvalRecord`
- `recorder.py`
  - 负责 run 生命周期记录与落盘
- `scorer.py`
  - 负责规则评分
- `registry.py`
  - 负责维护 `runs_index.json`

### 10.2 与 agent core 的集成点

核心集成点在：

- `agent_system/agent/core.py`

需要做的事情：

#### A. run 开始

在 `run()` 开头：

- 生成 `run_id`
- 初始化 recorder
- 记录 `run_started`

#### B. iteration 记录

在每轮迭代开始时：

- 记录 `iteration_started`

#### C. LLM 调用记录

在 `llm_client.chat()` 调用前后记录：

- `llm_call_started`
- `llm_call_finished`

记录字段：

- model
- provider
- latency
- usage（如果可得）

#### D. tool 调用记录

在执行工具前后记录：

- `tool_call_started`
- `tool_call_finished`

同时附加：

- tool_name
- arguments
- duration
- status

#### E. 技能注入记录

当 skill injector 成功时：

- 记录 `skill_injected`

#### F. 文件产物记录

在以下时机追加 `artifact_created`：

- `Write` 成功写文件
- `.tool-results` 成功持久化
- `output/` 出现新文件

#### G. run 完成

在结束时：

- 生成 `run.json`
- 生成 `eval.json`
- 更新 `runs_index.json`

### 10.3 是否需要改动 llm_client.py

需要，但只做最小改动。

目标：

- 尝试提取 provider 返回的 usage / model 信息
- 若拿不到，则字段置 `null`

要求：

- 不因为 usage 缺失而影响主流程

### 10.4 API 设计

建议在 `server/app.py` 增加以下接口：

#### 1. `GET /sessions/{session_id}/runs`

返回当前 session 的 run 列表。

#### 2. `GET /sessions/{session_id}/runs/{run_id}`

返回 `run.json`。

#### 3. `GET /sessions/{session_id}/runs/{run_id}/trajectory`

返回解析后的 trajectory 事件数组。

#### 4. `GET /sessions/{session_id}/runs/{run_id}/eval`

返回 `eval.json`。

#### 5. `GET /evaluation/runs`

返回跨 session 的最近运行列表，来源于 `runs_index.json`。

#### 6. `GET /evaluation/tasks`

返回本地任务定义列表。

### 10.5 SSE 是否需要增强

建议增强，但不必推翻现有协议。

做法：

- 保留当前 `thinking/tool_call/tool_result/response` SSE
- 在完成事件里附加 `run_id`
- 可选新增一个 `trajectory_event` 类型，供前端未来更细粒度消费

`Phase 1` 最小要求：

- `done` 事件里带 `run_id`

这样前端可以在一次对话结束后自动拉取本次 run 的详情。

## 11. 前端实施方案

### 11.1 组件建议

建议新增：

```text
frontend/src/copilot/components/
  TrajectoryPanel.tsx
  EvaluationPanel.tsx
  RunSummaryCard.tsx
  TimelineView.tsx
  RunsTable.tsx
```

### 11.2 WorkspacePanel 改造

当前 `WorkspacePanel.tsx` 以文件树为主。  
建议改造方向：

- `文件系统`
  - 保留现有树与预览
- `Skill`
  - 保留只读 skill 浏览
- `Trajectory`
  - 展示当前 session 最近一次 run 的摘要与时间线
- `Evaluation`
  - 展示当前 session / 全局最近 run 列表

### 11.3 ChatLayout 改造

建议在 `ChatLayout.tsx` 增加：

- `activeRunId`
- `recentRuns`
- `runLoading`
- `runError`

流程：

1. 发起请求
2. 正常接收 SSE
3. `done` 事件带回 `run_id`
4. 前端自动请求：
   - `GET /sessions/{session_id}/runs/{run_id}`
   - `GET /sessions/{session_id}/runs/{run_id}/trajectory`
   - `GET /sessions/{session_id}/runs/{run_id}/eval`
5. 更新 `Trajectory` / `Evaluation` 面板

### 11.4 TrajectoryPanel 设计

建议布局：

#### 顶部摘要

- 状态
- 耗时
- 轮数
- 工具数
- 错误数

#### 中部时间线

每步显示：

- 类型
- 标题
- 耗时
- 关键信息摘要

#### 底部快捷证据

- `chat.log`
- `history.json`
- `temp/*.py`
- `.tool-results/*.txt`

### 11.5 EvaluationPanel 设计

`Phase 1` 只做最小版本：

#### A. 当前会话最近运行

表格列：

- 时间
- task
- 状态
- 耗时
- 工具数
- 总分

#### B. 与上一次运行对比

仅比较：

- 耗时变化
- 工具数变化
- 错误数变化
- 总分变化

#### C. 全局最近运行

读取 `/evaluation/runs`

## 12. 推荐实施顺序

### Step 1：后端数据模型与 recorder

先做：

- `models.py`
- `recorder.py`
- run 落盘
- trajectory 落盘

先不要管前端。

### Step 2：规则评分与 runs_index

再做：

- `scorer.py`
- `registry.py`
- `eval.json`
- `runs_index.json`

### Step 3：API

补：

- runs 查询接口
- trajectory 查询接口
- eval 查询接口

### Step 4：前端 types 与 API 封装

补：

- `frontend/src/types.ts`
- `frontend/src/lib/api.ts`

### Step 5：右侧面板 UI

实现：

- `TrajectoryPanel`
- `EvaluationPanel`
- `WorkspacePanel` 标签调整

### Step 6：SSE 联动

最后补：

- `done` 事件带 `run_id`
- 前端自动刷新本次 run

## 13. 测试建议

### 13.1 后端测试

至少覆盖：

- run 目录创建
- trajectory 事件写入
- eval 文件生成
- runs_index 更新
- API 返回正确
- 异常 run 能正确写 `failed` 状态

### 13.2 前端测试 / 验证

至少验证：

- 会话结束后 `Trajectory` 面板自动刷新
- 会话结束后 `Evaluation` 面板自动刷新
- run 详情可以打开
- 时间线顺序正确
- 证据文件快捷入口可打开

### 13.3 手工回归用例

建议手工验证 3 条：

1. 正常 CSV 分析任务
2. 工具失败任务
3. skill 注入任务

## 14. 验收标准

完成 `Phase 1` 后，至少满足：

1. 每次任务执行后，session 下能生成 `runs/{run_id}` 目录
2. 目录下至少有：
   - `run.json`
   - `trajectory.jsonl`
   - `eval.json`
3. 前端右侧能看到 `Trajectory` 与 `Evaluation`
4. `Trajectory` 能展示本次运行摘要和时间线
5. `Evaluation` 能看到最近若干次运行并进行基础比较
6. 不依赖任何外部 eval 平台
7. 不影响现有聊天、workspace、文件查看主流程

## 15. 风险与注意事项

### 15.1 不要把所有日志都塞进 trajectory

trajectory 是结构化事件，不是 `chat.log` 的复制品。  
必须控制字段粒度，避免冗余。

### 15.2 不要让评分阻塞主流程

规则评分失败时：

- 允许 `eval.json` 缺省或降级
- 不能影响 agent 主运行结果

### 15.3 不要过早做复杂任务识别

`task_id` 第一版只要支持：

- 命中本地定义
- 否则 `adhoc`

### 15.4 不要在 Phase 1 引入云端依赖

这是明确边界。  
任何外部 eval 平台接入都推迟到后续阶段。

## 16. 给实现者的任务拆分建议

### 后端

- 新增 `agent_system/evaluation/models.py`
- 新增 `agent_system/evaluation/recorder.py`
- 新增 `agent_system/evaluation/scorer.py`
- 新增 `agent_system/evaluation/registry.py`
- 改 `agent_system/agent/core.py`
- 改 `agent_system/agent/llm_client.py`
- 改 `server/app.py`
- 改 `server/copilot_adapter.py`

### 前端

- 改 `frontend/src/types.ts`
- 改 `frontend/src/lib/api.ts`
- 改 `frontend/src/copilot/ChatLayout.tsx`
- 改 `frontend/src/copilot/components/WorkspacePanel.tsx`
- 新增 `TrajectoryPanel.tsx`
- 新增 `EvaluationPanel.tsx`
- 新增必要的子组件

### 文档

- 代码完成后回填：
  - 接口契约
  - 示例 JSON
  - 验收截图

## 17. 与 Phase 2 的衔接

`Phase 1` 做完后，`Phase 2` 就可以在此基础上继续：

- 固定任务集
- skill benchmark matrix
- 批量回放
- 引入外部 eval 平台

换句话说，`Phase 1` 的价值不是“做一个简化版评估”，而是：

**为后续 benchmark / skill eval / experiment 提供本地事实层。**
