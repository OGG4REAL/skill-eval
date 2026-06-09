# Phase 2-13: Evaluation API and UI

## Goal

把本地 benchmark 结果从 CLI 文件提升到 Studio 可查看对象。

## Status

Phase 1 API contract 已完成：

- 后端已暴露稳定 `/evaluation/*` contract。
- `BenchmarkStore` 负责 benchmark overview/list/detail summary。
- `SkillComparator` 负责 comparison summary 和 skill summary。
- 前端已新增类型和 API client。

尚未完成：Evaluation 页面还没有消费这些 contract 形成 benchmark / comparison 视图。

## Backend Scope

已新增或补齐 API：

- `GET /evaluation/overview`
- `GET /evaluation/benchmarks`
- `GET /evaluation/benchmarks/{benchmark_id}`
- `GET /evaluation/skills/{skill}/summary`
- `GET /evaluation/comparisons`
- `POST /evaluation/benchmarks/run`

返回内容以 `BenchmarkStore` 和 `SkillComparator` 为事实源，不在 API 层重算复杂逻辑。

Contract 边界：

- benchmark list 不返回 `_path`。
- benchmark detail 不透传完整 raw `cases`，只返回 `matrix`、`failed_cases`、`run_refs` 和 `comparison`。
- unknown skill summary 返回 200 空态。
- 缺失 benchmark detail 返回 404。
- benchmark run 是同步阻塞请求，不引入 job id、queue 或后台 worker。

## Frontend Scope

已完成：

- `frontend/src/types.ts` 新增 evaluation contract 类型。
- `frontend/src/lib/api.ts` 新增 overview、benchmark、skill summary、comparison、run benchmark typed API 调用。

下一步增加 Evaluation 视图能力：

- benchmark 列表。
- benchmark 详情。
- task x variant 聚合表。
- skill uplift summary。
- 失败 case 快速跳转到 Debug Lab run。

## Acceptance Criteria

- UI 可以从 benchmark 进入具体 run。
- result 指标优先展示，trajectory 指标只作为辅助列。
- API 对缺失 benchmark 返回明确 404。
- API 不暴露本地 benchmark 文件路径和完整 raw cases。
- 旧 `/evaluation/runs` 和 `/evaluation/tasks` 保持兼容。

## Verified

- `python -m pytest tests/test_benchmark_store.py tests/test_skill_comparator.py tests/test_evaluation_api_contract.py -q`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- Playwright smoke：页面初始化成功，console error 为 0，浏览器上下文可访问 `/evaluation/overview`、`/evaluation/benchmarks`、`/evaluation/benchmarks/{id}`、`/evaluation/comparisons`、`/evaluation/skills/{skill}/summary`。

注意：已运行的旧后端进程不会自动加载新增路由；默认 8001 服务需要重启。

## Out of Scope

- 图表美化优先级低于信息完整性。
- 不做在线启动 benchmark 的 UI。
- 不做权限、多用户或云端同步。
