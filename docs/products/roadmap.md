# Product Roadmap

## Done: Result-First Scoring and API Contract

已经完成：

- 让首批 task 的结果校验可信。
- 把 scoring 从 trajectory-first 切到 result-first。
- 在 benchmark aggregate 和 comparator 中突出 `result_score`、`result_pass_rate` 和 normalized gain。
- 暴露 Phase 1 `/evaluation/*` API contract。
- 前端新增 typed API client，但暂未改 Evaluation 页面骨架。

## Now: Evaluation UI

下一步做：

- benchmark 列表视图。
- benchmark 详情视图。
- task x variant matrix。
- skill uplift summary。
- failed case 到 Debug Lab run 的跳转。

暂不做：

- 在线启动 benchmark 的复杂 UI。
- 异步 job / queue / 状态轮询。
- 图表优先的复杂可视化。

## Next: Regression and Failure Cases

完成 Evaluation UI 后，再补：

- 失败案例沉淀。
- 回归任务集。

## Later: Routing and Versioned Skills

后续再做：

- skill routing / integration eval。
- `skill_v1` / `skill_v2` 对比。
- irrelevant skill 误触发评估。

## Explicitly Deferred

以下能力先不做：

- 外部 eval 平台对接。
- 自动 CI gate。
- LLM judge。
- 人工审核后台。
- 多租户权限模型。

## Final Closure

- Done: Phase 2-12 Result-First Verifier.
- Done: Phase 2-13 Evaluation API and UI.
- Done: Phase 2-14 Regression and Failure Cases.
- Done as minimal local loop: Routing and Versioned Skills.

Explicitly still deferred: external eval platform integration, automatic CI gate, LLM judge, human review backend, multi-tenant permissions, cloud sync, complex chart polish, and generic Agent benchmark platform.
