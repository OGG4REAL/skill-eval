# Evaluation Harness Architecture

## Goal

Evaluation harness 的目标是验证 skill 是否带来稳定、可解释、可重复的增益，而不是给通用 Agent 打一个抽象总分。

当前主线：

```text
fixed task
  -> no_skill / with_skill variants
  -> run records
  -> result-first scoring
  -> benchmark aggregate
  -> skill uplift comparison
```

## Core Modules

| 模块 | 职责 |
| --- | --- |
| `TaskLoader` | 严格加载 `evaluations/tasks/*.json`，校验 task schema |
| `VariantManager` | 解析 `no_skill` / `with_skill` / 版本化 variant 的实验条件 |
| `BenchmarkRunner` | 执行 task x variant x trial，写 benchmark JSON |
| `RuleScorer` | 计算 task-aware score，接入 result verifier |
| `ResultVerifier` | 面向最终结果校验 JSON 或脚本 stdout |
| `BenchmarkStore` | 读取 `evaluations/benchmarks/runs/*.json`，生成 overview / benchmark list / benchmark detail contract |
| `SkillComparator` | 计算 `with_skill - no_skill` 的 uplift，生成 comparison summary 和 skill summary contract |

## API Contract Surface

Phase 1 已把本地 benchmark JSON 提升为稳定 `/evaluation/*` API contract：

| Endpoint | 说明 |
| --- | --- |
| `GET /evaluation/overview` | Overview 第一屏 summary、最近 benchmark、comparison summary |
| `GET /evaluation/benchmarks` | benchmark 列表，每项包含 summary 和 comparison summary |
| `GET /evaluation/benchmarks/{benchmark_id}` | benchmark detail，包含 matrix、failed case summary、run refs、comparison |
| `GET /evaluation/skills/{skill}/summary` | skill 维度 summary；未知 skill 返回 200 空态 |
| `GET /evaluation/comparisons` | 默认全量 comparison；支持 `benchmark_id` 过滤单次 benchmark |
| `POST /evaluation/benchmarks/run` | 同步执行 benchmark；Phase 1 不引入 queue 或 job id |

边界：

- API 层不暴露 benchmark 本地文件路径。
- benchmark detail 不透传完整 raw `cases`。
- `/evaluation/runs` 和 `/evaluation/tasks` 保持兼容。
- 已启动的后端进程需要重启后才会加载新增路由。

## Current Task Schema Direction

任务定义以本地 JSON 为事实源，当前必须表达：

- `task_id`
- `group`
- `eval_type`
- `description`
- `input.user_query`
- `input.session_setup`
- `variants`
- `target_skills`
- `expected_signals`
- `expected_artifacts`
- `pass_criteria`
- `scoring_weights`
- `ground_truth`
- `verifier`

`verifier` 是 `phase2-12` 的关键字段。没有结果校验时，benchmark 只能说明过程健康，不能证明 task 结论可信。

## Variant Policy

当前可用主线：

- `no_skill`：不暴露业务 skill，作为 baseline。
- `with_skill`：暴露并预注入 target skill。

保留但未完整落地：

- `skill_v1`
- `skill_v2`
- `irrelevant_skill`

版本化 skill 和无关 skill 注入需要额外版本源或注入机制，不能在没有底层能力时假装支持。

## Scoring Direction

评分优先级：

1. `result_score` / `result_pass`
2. `task_success`
3. `signal_match`
4. `artifact_match`
5. `tool_efficiency`
6. `trajectory_quality`

Trajectory 是证据和调试材料，不再作为判断结果正确性的主线。
