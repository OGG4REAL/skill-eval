# Phase 2-14: Regression and Failure Cases

## Goal

把 Phase A 跑出的失败样本沉淀成可重复回归，避免 skill 和 scorer 后续漂移。

## Scope

- 固化失败 case 的 task 输入、期望输出和 verifier。
- 标记负增益任务。
- 为关键 bug 增加最小回归测试。
- 补充当前 task set 的覆盖说明。

## Failure Case Template

每个失败 case 至少记录：

- `task_id`
- `variant_id`
- `run_id`
- 失败类型
- 预期结果
- 实际结果
- 需要修复的层：skill / prompt / scorer / runner / UI

## Acceptance Criteria

- 已知失败能被本地测试或 benchmark 稳定复现。
- 修复后 comparator 能显示对应 task 的 result uplift 变化。
- 文档明确哪些失败暂不修，避免重复排查。

## Out of Scope

- 不扩展成完整 defect tracking 系统。
- 不建立人工审核后台。
- 不把所有历史 adhoc run 回填成 benchmark。

## Final State

- 已固化 result verifier 失败回归：当最终 JSON 与 expected output 不一致时，`result_score=0.0`、`result_pass=false`、`task_success=0.0`。
- 已固化 failed case contract：benchmark detail 不返回 raw `cases`，但保留 `failed_cases[].run_id` 和 `failed_cases[].session_id`，可跳转 Debug Lab。
- 已固化负增益回归：with_skill 的 `avg_result_score` 低于 no_skill 时，comparator 标记 `verdict=negative`，并进入 skill summary 的 `negative_tasks`。
- 已修复并收口：结果校验失败被误认为 task 成功、失败 case 缺 Debug Lab run ref、负增益任务不稳定可见。
- 暂不修：历史 adhoc run 不回填为 benchmark；不建立缺陷跟踪后台；不做人工审核流。

## Regression Tests

- `tests/test_phase2_14_regression_failures.py`
- `tests/test_task_aware_scorer.py`
- `tests/test_benchmark_store.py`
- `tests/test_skill_comparator.py`
