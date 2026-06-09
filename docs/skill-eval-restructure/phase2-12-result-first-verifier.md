# Phase 2-12: Result-First Verifier

## Goal

把评分主线从过程信号转为结果校验。完成后，benchmark 的核心结论应能回答：

> with_skill 是否让最终结果更正确。

## Implementation Scope

- 使用 task 中的 `ground_truth` 和 `verifier` 字段。
- `ResultVerifier` 支持从 `final_response_json` 和 `script_stdout` 提取校验对象。
- `RuleScorer.score_task_run()` 写入：
  - `scores.result_score`
  - `metrics.result_pass`
  - `metrics.rubric_score`
  - `metrics.result_detail`
- `SkillComparator` 优先使用 result 指标计算 uplift。

## Acceptance Criteria

- 没有 verifier 的 task 明确标记 `configured=false`，不能伪装成结果可信。
- verifier 失败时，`task_success` 必须为 `0.0`。
- benchmark aggregate 包含 result 平均分和 result pass rate。
- comparator 输出 result uplift，并保留旧 weighted score 作为辅助参考。
- 至少覆盖首批 CSV 和 finance task 的结果校验。

## Tests

- `tests/test_task_aware_scorer.py`
- `tests/test_benchmark_runner.py`
- `tests/test_skill_comparator.py`
- 新增或补充 verifier 失败、JSON 提取、script stdout 合并场景。

## Out of Scope

- LLM-as-a-Judge。
- 人工 rubric 标注后台。
- routing precision / recall。
- skill 版本仓库。
