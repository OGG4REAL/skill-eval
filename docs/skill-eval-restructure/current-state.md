# Current State

## Completed

当前已具备：

- `RunRecorder` 写入 `run.json`、`trajectory.jsonl`、`artifacts.json`、`eval.json`。
- `RunsRegistry` 维护跨 session 的 run 索引。
- `TaskLoader` 严格加载 `evaluations/tasks/*.json`。
- `VariantManager` 支持 `no_skill` / `with_skill` 主线。
- `BenchmarkRunner` 能执行 `task x variant x trial`。
- `BenchmarkStore` 能读取 benchmark 结果。
- `SkillComparator` 能计算 task delta 和 skill uplift。
- `BenchmarkStore` 已提供 overview/list/detail API contract helper，过滤本地路径和 raw cases。
- `SkillComparator` 已提供 comparison summary 和 skill summary contract helper。
- FastAPI 已暴露 Phase 1 evaluation contract：`/evaluation/overview`、`/evaluation/benchmarks`、`/evaluation/benchmarks/{id}`、`/evaluation/skills/{skill}/summary`、`/evaluation/comparisons`、`/evaluation/benchmarks/run`。
- 前端已新增 typed API client 和 contract types，但尚未改 Evaluation 页面骨架。
- 前端 Debug Lab 能查看 workspace、run、trajectory、eval 和 artifacts。

## Current Problem

Phase A 第一段已经证明“能跑”，Phase 2-12 已把评分主线推进到 result-first，Phase 1 API contract 也已经落地。

当前剩余问题在于：

- Evaluation 页面仍主要展示 run 列表，没有消费新的 benchmark / comparison contract。
- API contract 已能服务前端，但默认 8001 后端进程需要重启后才会加载新增路由。
- trajectory 仍是 Debug Lab 证据，不应提升为最终评估主线。

## Current Priority

进入 `phase2-13` 的 UI 消费阶段：

- 用现有 typed API client 接入 benchmark 列表、benchmark 详情和 comparison summary。
- 让 Evaluation 视图优先展示 `result_score`、`result_pass_rate`、normalized gain。
- 从 benchmark / failed case 快速跳转到 Debug Lab run。

## Current Non-Priority

暂不优先：

- routing eval。
- 新增大量任务。
- 外部 eval 平台。
- LLM judge。
- 前端复杂可视化。
- 异步 benchmark job / queue。

## Final Roadmap Closure

- Phase 2-12 已收口：scoring 主线为 result-first，trajectory 仅作为 Debug Lab 证据。
- Phase 2-13 已收口：`/evaluation/*` contract 稳定，EvaluationPanel 消费 typed evaluation client 展示 overview、benchmark list/detail、matrix、skill uplift、failed cases。
- Phase 2-14 已收口：关键失败样本已进入回归测试，负增益任务可由 comparator 稳定标记。
- Later roadmap 已完成最小闭环：routing eval 使用技能可见但不预注入；`skill_v1`/`skill_v2` 通过 task 显式本地目录映射比较；`irrelevant_skill` 通过 task 显式干扰 skill 评估误触发。
- 仍后置：外部 eval 平台、CI gate、LLM judge、人工审核后台、多租户权限、云端同步、复杂图表和通用 Agent benchmark 平台。
