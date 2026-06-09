# Skill Eval Studio Product Direction

## Positioning

`Skill Eval Studio` 是一个面向可插拔 skills 的本地评估和复盘工作台。它回答三个问题：

1. 某个 skill 是否让任务结果更好。
2. Agent 是否正确使用了 skill。
3. 失败时能否通过 run、trajectory、artifact 和 workspace 快速定位原因。

## Product Objects

一等对象：

- `Skill`：被评估的能力资产。
- `Benchmark`：一次固定任务集和 variant 的批量运行。
- `Variant`：实验条件，如 `no_skill` / `with_skill`。
- `Run`：单次任务执行。
- `Comparison`：skill uplift、task delta 和失败归因。

Debug Lab 对象：

- `Session`：运行容器和工作区。
- `Trajectory`：run 的过程证据。
- `Artifact`：run 生成的文件证据。

## Current UX Direction

- `Debug Lab` 保留为 run 复盘入口，不提升为主产品首页。
- `Workspace` 面板用于看 session 文件、run trace、run eval 和 artifact。
- `Evaluation` 面板后续应提升 benchmark / skill 对比，而不是只列最近 run。
- 产品文案避免把 trajectory 当作最终评估对象；它是定位问题的材料。

## Non-Goals

当前阶段不做：

- 通用 Agent benchmark 平台。
- 云端 experiment 管理。
- LLM-as-a-Judge。
- 人工标注工作流。
- 多模型横向 leaderboard。
- 复杂评估 DSL。
