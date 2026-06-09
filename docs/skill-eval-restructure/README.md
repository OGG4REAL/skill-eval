# Skill Eval Restructure

本目录是当前 spec coding 的施工入口。

## Current Direction

当前不是重做 Phase 2，也不是继续扩大 task 数量。Phase A 主链路已经能跑，result-first scoring 和 Phase 1 API contract 已落地，下一步是让 Evaluation UI 消费这些 contract。

当前优先级：

1. [current-state.md](current-state.md)
2. [phase2-12-result-first-verifier.md](phase2-12-result-first-verifier.md)
3. [phase2-13-evaluation-api-and-ui.md](phase2-13-evaluation-api-and-ui.md)
4. [phase2-14-regression-and-failure-cases.md](phase2-14-regression-and-failure-cases.md)

## Implementation Rule

- 不先做 routing。
- 不先接外部平台。
- 不先扩更多 benchmark 维度。
- 先让 Evaluation 页面展示可信 result 指标和 benchmark 对比。
- 不把同步 benchmark run 提前扩成 queue / job 系统。
