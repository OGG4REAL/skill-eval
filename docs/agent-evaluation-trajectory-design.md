# Agent Studio 评估体系设计与 Trajectory 方案

## 1. 文档目的

这份文档面向两个目标：

- 帮项目成员建立对 **Agent Evaluation** 的基础认知，知道为什么要做评估、在评什么、常见方法有哪些。
- 结合当前 `Agent Studio` 的实际代码形态，设计一套 **先能跑、可解释、可比较、可逐步扩展** 的 `trajectory + 最小 eval` 方案。

这不是一份“大而全的评测平台设计”，而是一份面向当前项目阶段的落地文档。

本文的核心判断是：

- `trajectory` 是让单次运行可观察。
- `eval` 是让多次运行可比较。
- `skill eval` 是让“能力模块是否真的带来增益”可验证。
- 当前项目不适合先全自建评测平台，更适合采用：

```text
本地薄数据层（run / trajectory / eval / benchmark）
                +
外部评估框架（优先 LangSmith，备选 Langfuse）
```

## 2. Agent 评估入门

### 2.1 什么是 Agent 评估

传统 LLM 应用的评估，常常聚焦在“最终回答是否正确”。  
但 Agent 系统比纯问答复杂得多，因为它会：

- 多轮思考
- 调工具
- 读写文件
- 产生中间产物
- 在不同步骤之间维护状态

因此，评估 Agent 时不能只看最终回答，还要看：

- 它是如何得到这个结果的
- 路径是否高效
- 工具使用是否合理
- 错误能否被恢复
- 产物是否完整

这就是为什么 Agent 评估天然包含两层：

1. **结果层评估**
   - 最终答案对不对
   - 是否完成了任务
2. **过程层评估**
   - 工具选择是否合理
   - 参数是否正确
   - 轨迹是否偏离预期
   - 成本、耗时、轮数是否异常

### 2.2 什么是 Trajectory

`trajectory` 可以理解为 **Agent 完整运行轨迹**。  
它不是一条日志，而是一条可分析的执行链。

一个典型 trajectory 可能包含：

1. 用户输入
2. 第 1 轮 LLM 思考
3. 调用 `Read` 读取 CSV
4. 工具返回结果
5. 第 2 轮 LLM 思考
6. 调用 `Write` 生成脚本
7. 调用 `Bash` 执行脚本
8. 返回最终答案

在当前项目中，这类数据已经以“松散形态”存在于：

- `history.json`
- `chat.log`
- `.tool-results/*.txt`
- `temp/*.py`
- 前端 SSE 事件流

但这些还不是结构化 trajectory。

### 2.3 为什么只看单次对话不够

如果只做单次会话可视化，你能回答：

- 这次为什么成功
- 这次为什么失败
- 这次慢在哪一步

但你回答不了：

- 这次改 prompt 后，是否真的比上一版更好
- 同一个任务在不同版本间有没有提升
- 某个 skill 是不是只是“偶尔有效”
- 某个能力是否稳定改善

所以：

- `trajectory` 解决“单次运行可解释”
- `eval` 解决“多次运行可比较”

### 2.4 Agent Eval 的几种常见方法

#### A. 规则评估（Programmatic / Rule-based）

通过规则直接判断：

- 是否调用了预期工具
- 是否生成了预期文件
- 是否出现报错
- 是否包含某类结构化结果

优点：

- 成本低
- 结果稳定
- 易于解释

缺点：

- 很难评估“答案质量”
- 容易过于刚性

适合当前项目的第一阶段。

#### B. LLM-as-a-Judge

让另一个模型按 rubric 对输出或轨迹评分。

例如：

- 最终回答是否覆盖了用户需求
- 工具路径是否合理
- 是否有不必要的步骤

优点：

- 更灵活
- 适合复杂开放任务

缺点：

- 成本更高
- 结果波动更大
- 调试和解释门槛更高

适合作为第二阶段增强，而不是第一阶段基础设施。

#### C. Trajectory Match / 轨迹匹配

给定一条参考轨迹，判断 Agent 实际路径与其是否一致或相近。

常见模式：

- `strict`：严格一致
- `unordered`：工具集合一致但顺序可放宽
- `subset`：没有多余工具
- `superset`：至少包含关键步骤

适合：

- 确定性较强的工作流任务
- tool-use 明确的场景

#### D. 离线实验（Offline Experiments）

把任务收集成 dataset，反复跑，比较版本差异。

这一步是把“体感优化”变成“实验优化”的关键。

## 3. 当前项目的现状与机会

### 3.1 当前已有基础

当前项目已经具备构建评估体系的若干基础：

#### 1. Session 目录天然隔离

会话目录结构已经比较清晰：

- `sessions/{session_id}/uploads`
- `sessions/{session_id}/output`
- `sessions/{session_id}/temp`
- `sessions/{session_id}/.tool-results`
- `sessions/{session_id}/chat.log`
- `sessions/{session_id}/history.json`

#### 2. 后端已有 Workspace 逻辑映射

`server/app.py` 已经把逻辑 `/workspace` 映射到这些会话目录。

#### 3. Agent 已有中间事件

`agent_system/agent/core.py` 在运行中已经产生：

- `thinking`
- `tool_call`
- `tool_result`
- 日志与工具执行痕迹

#### 4. 前端已有过程展示入口

`ThinkingPanel` 已经能展示步骤流，说明 UI 上已有“过程展示”的承载位置。

### 3.2 当前缺失的关键层

当前真正缺的不是“日志”，而是以下 4 个结构化对象：

1. `run`
   - 一次任务执行的主对象
2. `trajectory`
   - 一次 run 的步骤事件流
3. `eval`
   - 一次 run 的汇总评分
4. `skill benchmark`
   - 同一任务在不同 skill / variant 下的横向比较

### 3.3 当前最不建议做的事

当前阶段不建议：

- 一上来做全平台级评测系统
- 一上来接多个评估框架
- 一上来做复杂 LLM judge 流水线
- 一上来追求通用化 skill 评估 DSL

原因很简单：

- 任务集还不稳定
- rubric 还没沉淀
- 目前更需要先把“可观察 + 可比较”打通

## 4. 设计目标

本轮设计希望解决 5 个问题：

1. 单次运行发生了什么，能否清楚回放
2. 多次运行之间，能否自动比较而非人肉比较
3. 技能（skills）到底有没有提升能力，能否量化
4. 是否可以从 demo 演示平滑走向实验驱动迭代
5. 是否能在不重构现有系统的前提下逐步落地

对应原则：

- **薄层优先**：先补结构化数据，不先造大平台
- **结果 + 过程并重**：既看 final answer，也看 trajectory
- **以任务集为中心**：先有 task benchmark，再谈泛化评估
- **以 skill 为变体而非文档**：skill 的价值通过任务结果验证
- **本地证据保留**：保留本地文件、脚本、日志作为可追溯证据

## 5. 总体方案

### 5.1 方案摘要

推荐方案：

```text
Agent Runtime
  -> 生成 run 元数据
  -> 生成 trajectory 事件流
  -> 生成 eval 汇总
  -> 写入 session 目录
  -> 前端 Agent Studio 展示
  -> 可选同步到外部框架（LangSmith / Langfuse）
```

### 5.2 为什么不是纯自建

纯自建会很快撞上这些问题：

- dataset 怎么管理
- experiment 怎么复跑
- 版本怎么比较
- 评分器怎么迭代
- 人工标注怎么接

这些不是你当前项目最值得消耗时间的地方。

### 5.3 为什么也不能完全依赖外部框架

因为 `Agent Studio` 有自己独特的产品语义：

- 本地 `workspace`
- 本地 `.tool-results`
- 本地 `temp/*.py`
- 本地 `chat.log`
- 本地 `history.json`

外部框架可以做实验与评分，但替代不了你产品内的“轨迹与证据展示”。

所以最优分层是：

- **本地自建产品层**
- **外部接评估框架层**

## 6. 数据模型设计

### 6.1 核心对象一：Run

`run` 表示一次可比较的任务执行。

建议最小结构：

```json
{
  "run_id": "run_20260319_001",
  "session_id": "8849126355554f098cad546d60256a6e",
  "task_id": "csv_analysis_basic",
  "variant_id": "baseline",
  "skill_variant": ["csv-data-summarizer"],
  "trigger": "manual",
  "user_input": "分析我上传的 csv",
  "started_at": "2026-03-19T10:20:00Z",
  "finished_at": "2026-03-19T10:20:18Z",
  "duration_ms": 18342,
  "status": "passed"
}
```

字段说明：

- `task_id`
  - 当前 run 对应哪类任务
- `variant_id`
  - 当前版本标签，例如 `baseline`、`prompt_v2`
- `skill_variant`
  - 本次参与的 skill 列表
- `trigger`
  - `manual` / `replay` / `benchmark`

### 6.2 核心对象二：Trajectory

建议使用 `trajectory.jsonl`，一行一个事件，适合追踪和回放。

示例：

```json
{"run_id":"run_001","step_index":1,"type":"thinking","started_at":"2026-03-19T10:20:00Z","finished_at":"2026-03-19T10:20:01Z","duration_ms":940,"status":"success","message":"第 1 轮思考..."}
{"run_id":"run_001","step_index":2,"type":"tool_call","name":"Read","arguments":{"path":"/workspace/uploads/test.csv"},"started_at":"2026-03-19T10:20:01Z","finished_at":"2026-03-19T10:20:01Z","duration_ms":8,"status":"success"}
{"run_id":"run_001","step_index":3,"type":"tool_result","name":"Read","artifact_paths":[],"started_at":"2026-03-19T10:20:01Z","finished_at":"2026-03-19T10:20:01Z","duration_ms":5,"status":"success","message_excerpt":"month,year,..."}
{"run_id":"run_001","step_index":4,"type":"tool_call","name":"Write","arguments":{"path":"/workspace/temp/analysis_001.py"},"started_at":"2026-03-19T10:20:02Z","finished_at":"2026-03-19T10:20:02Z","duration_ms":12,"status":"success"}
{"run_id":"run_001","step_index":5,"type":"tool_call","name":"Bash","arguments":{"command":"python /workspace/temp/analysis_001.py"},"started_at":"2026-03-19T10:20:03Z","finished_at":"2026-03-19T10:20:08Z","duration_ms":5120,"status":"success","artifact_paths":["/workspace/.tool-results/call_xxx.txt"]}
{"run_id":"run_001","step_index":6,"type":"final_response","started_at":"2026-03-19T10:20:08Z","finished_at":"2026-03-19T10:20:18Z","duration_ms":10220,"status":"success"}
```

推荐事件类型：

- `thinking`
- `llm_call`
- `tool_call`
- `tool_result`
- `client_side_tool`
- `artifact_created`
- `final_response`
- `error`

其中 `llm_call` 建议单独作为事件保留，便于后续记录：

- `model`
- `temperature`
- `max_tokens`
- `prompt_tokens`
- `completion_tokens`
- `latency_ms`

### 6.3 核心对象三：Eval

`eval.json` 用于保存一次 run 的汇总评分。

示例：

```json
{
  "run_id": "run_001",
  "task_id": "csv_analysis_basic",
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
    "artifact_completeness": 1,
    "trajectory_quality": 0.78
  },
  "notes": []
}
```

第一版只建议做 4 个 score：

- `task_success`
- `tool_efficiency`
- `artifact_completeness`
- `trajectory_quality`

其中：

- `task_success`
  - bool 或 `0/1`
- `tool_efficiency`
  - 与多余工具调用、失败工具数有关
- `artifact_completeness`
  - 是否生成预期产物
- `trajectory_quality`
  - 先用规则近似，不必上来就 LLM judge

### 6.4 核心对象四：Runs Index

为了支持跨会话比较，建议维护一个轻量索引：

- `sessions/runs_index.json`
  - 或更合理地放到单独目录如 `evaluations/runs_index.json`

示例：

```json
[
  {
    "run_id": "run_001",
    "session_id": "8849126355554f098cad546d60256a6e",
    "task_id": "csv_analysis_basic",
    "variant_id": "baseline",
    "skills": ["csv-data-summarizer"],
    "status": "passed",
    "score": 0.84,
    "duration_ms": 18342,
    "created_at": "2026-03-19T10:20:18Z"
  }
]
```

这个索引的价值很高，因为它能直接支持：

- 最近运行列表
- 同任务对比
- 同 skill 对比
- 成功率趋势

### 6.5 Skill Benchmark Matrix

skill eval 不建议直接评 `SKILL.md`，而应该评：

**在一组固定任务上，这个 skill 是否带来稳定增益。**

因此建议单独设计：

- `skill_benchmarks/{skill_name}/{benchmark_name}.json`

核心结构是一个矩阵：

| task_id | no_skill | skill_v1 | skill_v2 |
|---|---:|---:|---:|
| csv_analysis_basic | 0.62 | 0.85 | 0.91 |
| csv_analysis_dirty_headers | 0.44 | 0.77 | 0.82 |
| csv_analysis_large_file | 0.31 | 0.64 | 0.71 |

每个单元格都能指向具体 run。

## 7. UI / 信息架构设计

### 7.1 总体建议

当前右侧 `Workspace` 的 `工件` 与 `调试` 一级 tab 价值偏低。  
如果引入 trajectory / eval，建议重构右侧信息架构，而不是继续堆在“调试”之下。

推荐方向：

- `文件系统`
- `Skill`
- `Trajectory`
- `Evaluation`

其中：

- `文件系统`：真实文件与证据
- `Skill`：当前 skill 说明与只读资源
- `Trajectory`：本次运行过程
- `Evaluation`：多次运行比较与 benchmark

### 7.2 Trajectory 面板

`Trajectory` 面板应该从“日志入口”升级为“运行轨迹入口”。

建议分 4 块：

#### A. 运行摘要卡片

展示：

- Run ID
- Task ID
- 版本标签
- 是否成功
- 总耗时
- 轮数
- 工具数
- 错误数

#### B. 时间线

每一步显示：

- step index
- 类型
- 名称
- 开始时间
- 耗时
- 状态
- 关键信息摘要

#### C. 关键证据

与本 run 关联的文件快捷入口：

- `chat.log`
- `history.json`
- `.tool-results/*.txt`
- `temp/*.py`

#### D. 差异提示

与最近基线比较：

- 总耗时变化
- 工具数变化
- 错误数变化
- 是否少走了一轮

### 7.3 Evaluation 面板

`Evaluation` 面板负责“跨 run 可比较”。

建议包含：

#### A. 最近运行表

列：

- 时间
- task
- variant
- skills
- 状态
- 总分
- 耗时
- 工具数

#### B. 任务对比视图

选择 `task_id` 后比较不同版本：

- baseline
- prompt_v2
- memory_fix
- with_skill
- without_skill

#### C. Skill Benchmark Matrix

对 skill 级评估非常关键。

展示：

- 行：任务
- 列：skill 版本
- 单元格：得分、状态、可点进 run

#### D. 指标趋势

可以先只做 3 条趋势：

- 成功率
- 平均耗时
- 平均工具调用数

## 8. 指标体系设计

### 8.1 第一阶段必须有的指标

#### 1. 任务成功率

定义：

- 任务是否完成
- 是否满足最小产出标准

#### 2. 耗时

包括：

- 总耗时
- 首次工具调用耗时
- 最终完成耗时

#### 3. 工具效率

包括：

- 工具调用次数
- 失败次数
- 无效调用比例

#### 4. 产出完整性

包括：

- 是否生成预期文件
- 是否触发预期图表/表格
- 是否出现预期结构化结果

### 8.2 第二阶段可加入的指标

- token 消耗
- API 成本
- 轨迹偏离度
- LLM judge correctness
- Hallucination risk
- Recovery ability

### 8.3 不建议第一阶段就做的指标

- 复杂综合总分
- 通用“智能度评分”
- 模糊的“体验分”

这些容易不可解释，且很难稳定。

## 9. Task Benchmark 设计

### 9.1 为什么先做任务集

评估体系的核心不是框架，而是：

- 你究竟要 Agent 稳定完成哪些任务

没有任务集，就没有稳定 benchmark。

### 9.2 当前项目推荐的第一批任务

建议先固定 5 到 10 个任务，这里给一版最小集合：

#### 1. `csv_analysis_basic`

- 输入：标准结构 CSV
- 期望：
  - 成功读取 `uploads/*.csv`
  - 至少出现一次图表或表格相关客户端工具
  - 最终回复非空

#### 2. `skill_explanation`

- 输入：询问某个 skill 的能力
- 期望：
  - 正确读取 `SKILL.md`
  - 返回结构化介绍

#### 3. `temp_script_generation`

- 输入：要求生成并执行脚本
- 期望：
  - `temp/*.py` 出现
  - `Bash` 成功执行

#### 4. `tool_result_persistence`

- 输入：产生大输出
- 期望：
  - `.tool-results/*.txt` 出现

#### 5. `workspace_history_resume`

- 输入：切 session 后继续追问
- 期望：
  - 能恢复并利用历史上下文

### 9.3 每个任务建议的最小定义

```json
{
  "task_id": "csv_analysis_basic",
  "input": "分析我上传的 csv",
  "expected_signals": [
    "Read:/workspace/uploads/*.csv",
    "client_tool:render_chart|render_table"
  ],
  "pass_criteria": {
    "final_response_non_empty": true,
    "tool_errors_max": 0,
    "artifact_required": false
  }
}
```

## 10. Skill Eval 设计

### 10.1 Skill Eval 的正确对象

不要评：

- `SKILL.md` 写得是否优美

要评：

- 在一组固定任务上，这个 skill 是否稳定提升了目标能力

也就是说：

```text
Skill = 可实验的能力变体
而不是一份静态文档
```

### 10.2 Skill Eval 的四个维度

#### A. Skill Selection Accuracy

任务出现时，是否应该触发该 skill。

例如：

- CSV 分析任务是否注入 `csv-data-summarizer`
- 理财问题是否注入 `fin-advisor-math`

#### B. Skill Lift

开 skill 与不开 skill，任务结果是否提升。

看：

- 成功率提升
- 耗时下降
- 工具数减少
- 错误数下降

#### C. Trajectory Improvement

skill 是否让路径更短、更合理。

#### D. Generalization

skill 是否只在少数 showcase case 有用，还是在一类任务上都稳定。

### 10.3 第一版 Skill Eval 如何做

第一版不建议做自动 LLM judge 的 skill 评分器。

先做：

- 固定任务集
- 开 / 关 skill 对照
- 比较：
  - 成功率
  - 耗时
  - 工具数
  - 关键产物

这就已经非常有价值。

## 11. 框架选型建议

### 11.1 选型原则

评估框架要回答两类问题：

1. 是否擅长 **agent / trajectory / tool use**
2. 是否支持 **dataset / experiment / compare**

### 11.2 LangSmith

优点：

- 已有明确的 trajectory evaluation 能力
- 非常适合 agent / tool use / experiment
- dataset + experiment + compare 路径清晰

适合当前项目的点：

- 你已经是 agent 系统，不是纯聊天
- 你很快会需要任务集对比和版本比较

不足：

- 无法替代你本地 `workspace` 证据视图

适合作为：

- 第一优先级的外部 eval 后端

### 11.3 Langfuse

优点：

- session / trace / observation / score 模型清晰
- 很适合 observability + 自定义评分
- 已公开有 Agent Skills Evaluation 的实践

适合当前项目的点：

- 如果你更重视 session、trace、score 与观测层

不足：

- 相比 LangSmith，开箱即用的 experiment workflow 稍弱一些

适合作为：

- 更偏观测和评分层的备选

### 11.4 OpenAI Evals

优点：

- 对 tool eval、trace grading、judge 类场景有指导

不足：

- 更像一套评估能力集合，不是最适合当前产品阶段的总框架

适合作为：

- Judge 或特定 evaluator 的补充能力

### 11.5 Braintrust

优点：

- 实验、scorer、对比能力强

不足：

- 对当前 `Agent Studio` 这种“产品内本地工作区 + 评估视图”的结合度没那么直接

适合作为：

- 后续想把 eval 更产品化、更规模化时再看

### 11.6 最终推荐

当前项目推荐：

```text
本地自建：
- run / trajectory / eval / skill_benchmark
- Agent Studio 内的 Trajectory / Evaluation 面板

外部优先：
- LangSmith（第一优先）

备选：
- Langfuse
```

### 11.7 敏感数据场景下的架构建议

如果后续评估会接触敏感数据，这里的“是否接外部 eval 平台”就不能只从功能便利性判断，还要从数据边界判断。

关键原则：

- **本地数据层必须先有**
- **外部平台不能成为唯一事实源**
- **是否同步到外部平台，应按数据敏感等级决定**

原因：

- 模型调用虽然已经是云端，但 eval / tracing 平台通常会保存更完整的上下文副本
- 这些副本往往包含：
  - 原始 prompt
  - 多轮历史
  - tool arguments
  - tool results
  - 文件路径
  - 中间脚本
  - 评分与人工标注
- 从安全视角看，trajectory 数据通常比最终回答更敏感

因此推荐将架构分成两层：

#### A. 事实源层（必须自控）

由项目自己保留：

- `run.json`
- `trajectory.jsonl`
- `eval.json`
- `runs_index.json`
- `skill_benchmark.json`

这是后续无论是否接第三方平台都必须存在的本地事实源。

#### B. 分析增强层（可插拔）

按需要同步到：

- `LangSmith`
- `Langfuse`
- 后续自托管方案

这样可以保证：

- 外部平台挂掉时不影响核心数据
- 未来迁移平台时不会丢历史
- 可以根据敏感等级决定哪些数据能上传

### 11.8 数据敏感度与平台选择建议

建议按数据等级处理：

#### L0：公开 / demo / 合成数据

- 可直接接云端 eval 平台
- 适合快速验证方法和熟悉 workflow

#### L1：内部非敏感数据

- 可接云端平台
- 建议做基础脱敏
- 不上传真实文件路径、用户标识、业务主键

#### L2：敏感业务数据

- 不建议直接上传原始 trajectory 到外部平台
- 可仅上传脱敏摘要或聚合指标
- 原始 run / trajectory / eval 仍留本地

#### L3：高敏 / 合规受限数据

- 仅保留本地或自托管
- 不接外部云端 eval 平台

### 11.9 当前项目的推荐决策

结合当前项目阶段，建议这样定：

#### 现在（Phase 1）

- **不接外部 eval 平台**
- 先把本地数据层做扎实：
  - `run`
  - `trajectory`
  - `eval`
  - `runs_index`
  - `skill_benchmark`
- 目标是先把：
  - 单次运行可回放
  - 多次运行可比较
  - skill 增益可观察

原因：

- 当前最缺的是结构化事实层，不是平台能力
- 先做外部接入会分散注意力
- 评估方法本身还在建立阶段
- 未来大概率会遇到敏感数据，过早绑定云端平台不划算

#### 后续（Phase 2 / Phase 3）

- 用 **demo 数据、脱敏数据、合成 benchmark 数据** 试接外部平台
- 首选 `LangSmith` 验证 trajectory eval / experiment workflow
- 如果后续更强调 session / trace / score 与自托管路线，再重点评估 `Langfuse`

## 12. 分阶段实施建议

### Phase 1：本地最小可用层

目标：

- 让单次运行可回放
- 让多次运行可比较
- 不引入外部 eval 平台依赖

交付：

- `run.json`
- `trajectory.jsonl`
- `eval.json`
- `runs_index.json`
- 右侧 `Trajectory` 面板
- 简单 `Evaluation` 面板
- 本地 task 定义与规则评分能力雏形

本阶段明确不做：

- 不接 `LangSmith`
- 不接 `Langfuse`
- 不做云端 trace 同步
- 不做 LLM judge

### Phase 2：固定任务集与 Skill Benchmark

目标：

- 让“技能是否带来提升”可比较

交付：

- `tasks/*.json`
- `skill_benchmarks/*.json`
- benchmark matrix 展示

### Phase 3：接 LangSmith

目标：

- 跑离线实验
- 做版本对比
- 用低敏或脱敏数据验证外部评估工作流

交付：

- dataset
- experiments
- baseline vs variant 报告

### Phase 4：引入 Judge

目标：

- 评估更开放的最终回答质量与轨迹质量

交付：

- 规则分 + LLM judge 混合评分

## 13. 当前项目的关键技术改动点

### 13.1 后端

建议新增或改造：

- `agent_system/agent/core.py`
  - 在运行过程中持久化结构化 trajectory 事件
- `agent_system/agent/llm_client.py`
  - 提取 `usage`、`latency` 等信息
- `server/app.py`
  - 暴露 `run`、`trajectory`、`eval` 查询接口
- `server/copilot_adapter.py`
  - 在 SSE 中区分结构化事件类型，便于前端和持久化共用

### 13.2 前端

建议新增：

- `TrajectoryPanel`
- `EvaluationPanel`
- `RunSummaryCard`
- `TimelineView`
- `BenchmarkMatrix`

### 13.3 数据落盘目录建议

当前 session 目录建议增加：

- `sessions/{session_id}/runs/{run_id}/run.json`
- `sessions/{session_id}/runs/{run_id}/trajectory.jsonl`
- `sessions/{session_id}/runs/{run_id}/eval.json`

统一 benchmark 建议单独目录：

- `evaluations/tasks/*.json`
- `evaluations/runs_index.json`
- `evaluations/skill_benchmarks/*.json`

## 14. 常见误区

### 误区 1：先做最复杂的评分体系

错误原因：

- 指标越多，不一定越有用
- 第一阶段最重要的是建立稳定基线

### 误区 2：只看最终回答

错误原因：

- Agent 的大量问题发生在工具选择、参数、路径和恢复能力上

### 误区 3：只做单次 run 可视化

错误原因：

- 没有横向比较，就无法验证优化是否有效

### 误区 4：把 Skill 当作文档来评

错误原因：

- 真正该评的是“skill 对任务表现的提升”

## 15. 结论

对 `Agent Studio` 而言，trajectory 与 eval 不是附加项，而是从“好看 demo”走向“可持续迭代系统”的必要基础。

最关键的设计结论有三条：

1. 先做 `trajectory`，把单次运行讲清楚
2. 再做最小 `eval`，把多次运行比较自动化
3. skill eval 不评文档本身，而评其在任务集上的增益

当前阶段最合理的路线不是大而全，而是：

```text
本地薄层 + 固定任务集 + 外部实验框架
```

这能让项目从“凭感觉优化”升级成“基于证据优化”。

## 16. 参考资料

### 官方文档 / 技术博客

1. LangSmith Trajectory Evaluations  
   https://docs.smith.langchain.com/langsmith/trajectory-evals

2. LangChain Docs: How to evaluate your agent with trajectory evaluations  
   https://docs.langchain.com/langsmith/trajectory-evals

3. LangChain Docs: Evaluation  
   https://docs.langchain.com/langsmith/evaluation

4. Langfuse Blog: Evaluating AI Agent Skills  
   https://langfuse.com/blog/2026-02-26-evaluate-ai-agent-skills

5. Langfuse Docs: Tracing Data Model  
   https://langfuse.com/docs/observability/data-model

6. Langfuse FAQ: What are scores and when should I use them?  
   https://langfuse.com/faq/all/what-are-scores

7. OpenAI Docs: Agent evals  
   https://platform.openai.com/docs/guides/agent-evals

8. OpenAI Cookbook: Getting started with evals  
   https://cookbook.openai.com/examples/evaluation/getting_started_with_openai_evals

9. OpenAI Cookbook: Evaluating Agents with Langfuse  
   https://cookbook.openai.com/examples/agents_sdk/evaluate_agents

10. Braintrust Docs: Experiments  
    https://www.braintrust.dev/docs/core/experiments

11. Braintrust Docs: Tracing  
    https://www.braintrust.dev/docs/guides/tracing

### 论文 / 研究

1. TRACE: Trajectory-Aware Comprehensive Evaluation for Deep Research Agents  
   https://arxiv.org/abs/2602.21230

2. TRAJECT-Bench: A Trajectory-Aware Benchmark for Evaluating Agentic Tool Use  
   https://arxiv.org/abs/2510.04550

3. Beyond the Final Answer: Evaluating the Reasoning Trajectories of Tool-Augmented Agents  
   https://openreview.net/forum?id=chLlLbI7de

### 阅读顺序建议

如果是第一次系统接触 Agent 评估，建议按这个顺序看：

1. 先读本文件的第 2、3、4 节，建立概念
2. 再看 LangSmith trajectory eval 官方文档，理解行业通用范式
3. 再看 Langfuse 的 skill eval 文章，理解 skill 级评估怎么做
4. 最后读 TRACE / TRAJECT-Bench 这类论文，建立更系统的视角
