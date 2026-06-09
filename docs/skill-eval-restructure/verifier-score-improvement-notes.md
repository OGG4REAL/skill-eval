# Skill Eval verifier 与 score 改进建议

## 结论

当前方向是正确的：Skill Eval 应继续坚持 result-first verifier，用最终结果证明 skill 是否真的有帮助，而不是用 trajectory 或内部信号当主评分依据。

下一步不应该做通用 eval 平台，也不应该引入 LLM judge。更适合的改法是：

1. 固定指标层级，让 UI 和 comparator 只用 result 指标做主结论。
2. 升级 verifier check 语义，区分核心必过项和辅助加分项。
3. 逐步把 CSV 类任务从 `script_stdout` 迁到 artifact JSON 校验。
4. 给每个 task 增加 oracle 说明，让 ground truth 和 verifier 可追溯。

## 当前问题

### `task_success` 太二元

`task_success` 现在适合作为 hard pass/fail：

- run 必须成功。
- `pass_criteria` 必须通过。
- 如果配置了 verifier，verifier 必须整体通过。

问题是：任何 verifier check 失败都会让 `task_success=0.0`。这适合判断“这次是否完全过关”，但不适合作为 skill uplift 的细粒度主指标。

建议：

- 保留 `task_success`。
- UI 中把它叫做“是否完全通过”或“hard pass”。
- 不再用它作为 skill 好坏的第一结论。

### `result_score` 依赖 task 质量

`result_score` 比 trajectory 可靠，但它依赖 task 的 `ground_truth`、字段权重和 verifier 设计。如果这些写得不好，分数会误导。

建议：

- 每个 task 必须说明 ground truth 来源。
- verifier check 尽量覆盖核心业务结果，不要只校验格式。
- 对新增 task 做最小人工 review：确认题目清楚、答案可复现、校验不过窄。

### `script_stdout` 作为结果通道偏间接

CSV task 现在通过 `script_stdout` 从 Bash 输出里提取 JSON。这个方式能跑通，但它把 trajectory 同时当成了 debug 证据和结果数据通道。

建议：

- 短期保留 `script_stdout`，保证现有 task 不破。
- 新增 verifier target：`artifact_json`。
- 约定 agent 输出结果到 `/workspace/temp/eval_result.json`。
- verifier 优先读 artifact JSON；trajectory 只用于 Debug Lab 解释过程。

## 建议的指标层级

### Skill 结论层

用于回答“这个 skill 有没有帮助”。

- `result_score_uplift`
- `result_pass_rate_uplift`
- `normalized_gain`

这三项应该是 Evaluation UI 的主视图指标。

### Task 结果层

用于回答“这个 task 本身是否完成”。

- `result_score`: 0 到 1 的部分分。
- `result_pass`: 核心必过 check 是否全部通过。
- `task_success`: run 成功 + pass_criteria 通过 + result_pass。

### Debug 诊断层

用于解释为什么失败，不作为主结论。

- `signal_match`
- `artifact_match`
- `tool_efficiency`
- `trajectory_quality`
- `weighted_score`

## verifier check 改进

当前 check 示例：

```json
{
  "id": "final_value",
  "type": "numeric_tolerance",
  "path": "final_value",
  "tolerance": 0.001,
  "tolerance_mode": "relative",
  "weight": 0.35
}
```

建议增加 `required`：

```json
{
  "id": "final_value",
  "type": "numeric_tolerance",
  "path": "final_value",
  "tolerance": 0.001,
  "tolerance_mode": "relative",
  "weight": 0.35,
  "required": true
}
```

语义：

- `required: true`: 核心正确性，失败则 `result_pass=false`。
- `required: false`: 辅助质量项，只影响 `result_score`，不决定 hard pass。
- 未声明 `required` 时默认 `true`，保持向后兼容。

这样可以避免一个次要字段失败就把整道题判死，同时保留严格的核心正确性判断。

## artifact JSON target

建议新增 verifier target：

```json
{
  "target": "artifact_json",
  "artifact_path": "/workspace/temp/eval_result.json"
}
```

执行逻辑：

1. BenchmarkRunner 仍正常跑 agent。
2. Agent 按 `output_contract` 要求写出 `/workspace/temp/eval_result.json`。
3. ResultVerifier 读取该 artifact。
4. verifier checks 对 artifact JSON 执行。
5. trajectory 只用于 Debug Lab，不再承担结果数据通道。

迁移策略：

- 现有 CSV task 继续支持 `script_stdout`。
- 新 CSV task 优先使用 `artifact_json`。
- 旧 task 可以逐个迁移，不需要一次性改完。

## oracle 字段

`oracle` 是 task 的参考解法或标准答案来源，不给 agent 看，只给我们维护 eval 时看。

建议先加轻量字段：

```json
{
  "oracle_notes": "用 pandas 读取 regional_sales_clean.csv，按 region groupby 求 revenue sum，East 最高，总收入 242560。"
}
```

以后如果需要再加：

```json
{
  "oracle_command": "python evaluations/oracles/csv_analysis_clean_general.py"
}
```

字段分工：

- `ground_truth`: 标准答案本身。
- `verifier`: 怎么检查 agent 的答案。
- `oracle_notes`: 标准答案怎么来的。
- `oracle_command`: 可复现标准答案的参考脚本。

第一步只建议做 `oracle_notes`，不要立刻做 oracle 脚本系统。

## 外部借鉴

### Anthropic agent evals

可借鉴点：

- task 是单个测试，有输入和成功标准。
- trial 是一次尝试。
- grader 负责评分。
- 一个 grader 可以包含多个 assertions/checks。

对本项目的启发：我们现在的 task、trial、verifier 方向是对的，但需要把 check 的语义做清楚。

参考：https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents

### Terminal-Bench

可借鉴点：

- 真实任务。
- 执行环境。
- verifier script。
- oracle solution。

对本项目的启发：Skill Eval 不应该只看回答是否像样，而应该让 agent 产出可验证结果，再由脚本或 deterministic verifier 判定。

参考：https://terminalbench.lol/

### SWE-bench Verified

可借鉴点：

- benchmark 本身也需要被验证。
- 题目描述不清或测试不合理，会让分数失真。

对本项目的启发：新增 task 时要记录 oracle/source，避免 ground truth 和 verifier 变成黑盒。

参考：https://openai.com/index/introducing-swe-bench-verified/

### LangSmith / Promptfoo

可借鉴点：

- dataset examples + evaluators。
- assertion-based output validation。
- evaluation feedback 包含 score 和 comment。

对本项目的启发：前端可以把概念包装成 task、evaluator、result，不暴露 variant/group；后端继续保持简单 JSON task 和 local verifier。

参考：

- https://docs.langchain.com/langsmith/evaluation-concepts
- https://www.promptfoo.dev/docs/configuration/expected-outputs/

## 推荐落地顺序

### Step 1: UI 和文案先收敛

- 主指标固定为 `result_score_uplift`、`result_pass_rate_uplift`、`normalized_gain`。
- `weighted_score`、signal、trajectory 放到高级详情。
- `task_success` 显示为 hard pass，不作为主结论。

### Step 2: verifier check 增加 `required`

- 默认 `required=true`，兼容旧 task。
- `result_pass` 只由 required checks 决定。
- `result_score` 仍按所有 weighted checks 算。

### Step 3: task 增加 `oracle_notes`

- TaskLoader 允许可选字段。
- 新增/迁移 task 时补上标准答案来源。
- UI 可在高级详情里展示。

### Step 4: 新增 `artifact_json` target

- 先实现 verifier 读取 `/workspace/temp/eval_result.json`。
- 新 CSV task 优先用 artifact JSON。
- 旧 `script_stdout` 保留兼容。

## 暂不做

- 不引入 LLM judge。
- 不做人工审核后台。
- 不做外部 eval 平台对接。
- 不做通用 eval DSL。
- 不做复杂可视化图表。
- 不做 oracle 脚本管理系统。

