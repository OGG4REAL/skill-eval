# Phase 2 实施规划：以 Skills Eval 为主线的 Benchmark 与 Harness

## 1. 文档定位

这份文档承接已经完成的 `Phase 1`，用于明确当前项目在 `Phase 2` 的评估主线、实施范围和落地顺序。

`Phase 1` 已经完成的能力是：

- `run.json`
- `trajectory.jsonl`
- `eval.json`
- `artifacts.json`
- `runs_index.json`
- `Trajectory / Evaluation` 前端面板

也就是说，当前系统已经具备：

- 单次运行可观测
- 运行过程可回放
- 最小规则评分可落盘

但仍然缺少：

- 固定任务集
- 批量 benchmark runner
- skill 对照实验能力
- 可追溯的 skill benchmark matrix

本文默认已阅读：

- `docs/agent-evaluation-trajectory-design.md`
- `docs/Agent&Skills_Evals/phase1-trajectory-eval-implementation-plan.md`

说明：

- 评估相关文档后续统一收敛到 `docs/Agent&Skills_Evals/`
- 为兼容旧引用，仓库根目录保留同名 `phase2` 文档副本

## 2. 当前结论先行

### 2.1 当前最重要的方向判断

经过本轮讨论，`Phase 2` 的方向明确调整为：

- **不把通用 Agent Eval 作为主线**
- **优先做 Skills Eval**
- **Skill Eval 评估的是“Agent 搭载 skill 后的表现增益”**
- **评估主管线先做本地薄 Harness，不先接外部平台**

原因很简单：

- 当前项目还没有稳定、清晰、足够覆盖的“通用 Agent 应用场景”
- 如果没有明确任务族与优化目标，通用 Agent 评估即使做出来，也很难指导后续优化
- 但 Skills 是当前系统已经存在、未来还会持续扩张的核心能力资产
- Skills 更适合做受控对照实验，能直接回答“这个 skill 值不值得继续投入”

### 2.2 `Phase 2` 要解决的问题

`Phase 2` 现在要解决的是：

1. 现在只有零散 `adhoc` run，缺少稳定任务集
2. 现在只能单次运行，缺少批量回放能力
3. 现在能看 run，但不能系统比较 skill 增益
4. 现在缺少对 `with_skill / without_skill / skill_v1 / skill_v2` 的统一实验框架
5. 现在没有真正的 eval harness，只有本地事实层和数据埋点

### 2.3 本阶段的核心交付

必须交付：

- 一组固定任务定义（第一版建议 5 到 10 个）
- 一套本地 `Skills Eval Harness`
- 一套 benchmark runner（本地 CLI 即可）
- 一套变体控制机制（`no_skill` / `with_skill` / `skill_v1` / `skill_v2`）
- 一套与任务绑定的规则评分能力
- `skill benchmark matrix`
- `Evaluation` 面板中的 benchmark / skill 对比入口

### 2.4 本阶段明确不做

`Phase 2` 明确不做：

- 不做大而全的通用 Agent Benchmark
- 不做云端 experiment 平台同步
- 不接 `LangSmith`
- 不接 `Langfuse`
- 不接 `Braintrust`
- 不接 `Phoenix`
- 不接 `Harbor`
- 不做 `LLM-as-a-Judge`
- 不做人工标注工作流
- 不做复杂评估 DSL
- 不做持续集成 gate

外部平台接入和更完整的 Agent Eval 放到后续阶段。

## 3. 为什么现在不把通用 Agent Eval 作为主线

### 3.1 当前阶段的现实约束

如果没有具体应用场景、明确任务边界和优化目标，通用 Agent Eval 会立刻遇到三个问题：

1. 不知道该测哪些任务
2. 不知道分数涨跌对应的优化方向是什么
3. 不知道这些分数和系统未来的真实价值是否相关

也就是说：

- 做出一个通用分数，并不代表能形成优化闭环
- 没有明确任务族时，Agent Eval 很容易变成“有分数，但不好用”

### 3.2 当前更适合的优化闭环

当前项目最容易建立闭环的是：

```text
Skill 设计
  -> 任务表现变化
  -> 可比较 benchmark
  -> 定位问题
  -> 迭代 skill
```

这条链路比“泛化 Agent 越测越大”更容易落地，也更符合当前项目阶段。

## 4. 评估对象拆分

虽然 `Phase 2` 主线是 Skills Eval，但必须从一开始就区分清楚评估对象。

### 4.1 Base Agent Eval

评估对象：

- 基座 Agent 本身的通用能力
- prompt / memory / tool orchestration / error recovery

当前结论：

- **现在不作为主线**
- 后续可做一套很薄的 regression suite
- 主要用于防回退，不用于当前阶段的主要优化决策

### 4.2 Skills Eval

评估对象：

- 同一个 Agent、同一个模型、同一个任务，在不同 skill 条件下的表现变化

当前结论：

- **这是 `Phase 2` 主线**
- 不直接评 `SKILL.md`
- 评的是 skill augmentation 是否带来稳定、可解释、可重复的增益

换句话说：

```text
Skills Eval = 固定 Agent × 固定模型 × 固定任务 × Skill 条件变化
```

### 4.3 Agent × Skill 集成 Eval

评估对象：

- Agent 会不会正确发现、选择、使用 Skill

关注问题：

- 该触发时是否触发
- 不该触发时是否误触发
- 激活后是否真的采用 Skill，而不是“看了但没用”

当前结论：

- 这是 `Phase 2` 的第二层能力
- 放在 Skills Uplift Eval 跑通之后推进

## 5. `Phase 2` 的三阶段设计：A / B / C

## 5.1 Phase A：Skills Uplift Eval

### 目标

先回答最重要的问题：

- 某个 Skill 有没有价值
- `with_skill` 是否优于 `without_skill`
- `skill_v2` 是否优于 `skill_v1`

### 核心实验条件

第一版建议支持：

- `no_skill`
- `with_skill`
- `skill_v1`
- `skill_v2`

可选但强烈建议预留：

- `irrelevant_skill`

`irrelevant_skill` 的意义是排除“只是多了上下文就涨分”的伪收益。

当前落地策略建议：

- schema 支持
- 文档保留
- 第一版实现可选

也就是 `Phase A v1` 先优先跑通：

- `no_skill`
- `with_skill`
- `skill_v1`
- `skill_v2`

`irrelevant_skill` 放在 uplift 跑通后补强。

### 任务类型

优先放入第一批任务的应该是：

- 典型 CSV 分析任务
- 典型 finance / math 任务
- 需要明显专业步骤的任务
- 明显“有 skill 时应该更好”的任务

### 关键指标

- `pass_rate`
- `avg_score`
- `success_lift`
- `efficiency_lift`
- `avg_duration_ms`
- `avg_tool_calls`
- `avg_tool_errors`
- `stability`
- `negative_delta_tasks`

### 产出

- benchmark run JSON
- skill benchmark JSON
- skill matrix
- task-level lift 汇总

### 结论价值

这一步完成后，至少应该能回答：

- 哪些 Skill 值得继续投入
- 哪些 Skill 在哪些任务上有效
- 哪些 Skill 会带来负增益

## 5.2 Phase B：Skill Routing / Integration Eval

### 目标

在 uplift 已经跑通之后，进一步回答：

- Agent 会不会正确使用 Skill
- Skill 路由是否可靠

### 核心实验问题

- 该触发时是否触发
- 不该触发时是否误触发
- 激活后是否真的遵循 Skill
- 多个 Skills 并存时是否会选错

### 任务类型

需要构建三类样本：

- 应触发 Skill 的样本
- 不应触发 Skill 的样本
- 容易混淆的近邻样本

### 关键指标

- `activation_precision`
- `activation_recall`
- `activation_f1`
- `wrong_skill_activation_rate`
- `missed_skill_rate`
- `post_activation_success_rate`

### 产出

- skill routing report
- 按 skill 的 precision / recall 汇总
- 误触发和漏触发 case 列表

### 结论价值

这一步完成后，应该能回答：

- Agent 是否已经具备“会用 Skill”的能力
- 当前问题主要在 Skill 本身，还是在 Skill 路由

## 5.3 Phase C：更完整的 Agent Eval 与外部平台接入

### 目标

当本地 Skills Eval Harness 稳定后，再逐步补：

- 更薄但更稳定的 Base Agent regression suite
- 外部 trace / experiment 平台
- 更复杂的长周期 benchmark

### 此阶段才考虑的事情

- 接 `Harbor`
- 接 `Braintrust`
- 接 `Phoenix`
- 接 `LangSmith`
- 接 `Langfuse`
- 更完整的通用 Agent Eval

### 原则

- 平台是承载层，不是方法本身
- 先有任务、变体、grader、聚合，再谈平台接入

## 6. `SkillsBench` 对本项目的借鉴结论

### 6.1 我们借鉴什么

借鉴 `SkillsBench` 的核心方法，而不是照搬其完整 benchmark：

- 使用配对实验，而不是绝对打分
- 评估对象是“Agent 搭载 skill 后的表现”
- 优先用 deterministic verifier / rule-based grader
- 关注 `with_skill` 相对 `without_skill` 的增益
- 允许 `skill_v1 / skill_v2` 横向比较

### 6.2 我们不直接照搬什么

当前阶段不直接照搬：

- 大规模容器化 benchmark 基础设施
- 多 harness 对比
- 社区级 benchmark 任务生态
- 高成本平台化部署

## 7. `Phase 2` 的总体设计

`Phase 2` 不是另起一套系统，而是在 `Phase 1` 的本地事实层上，加一层本地化的 Skills Eval Harness。

整体结构：

```text
任务定义 (evaluations/tasks/*.json)
    ↓
variant 控制 (no_skill / with_skill / skill_v1 / skill_v2)
    ↓
benchmark runner
    ↓
生成多次 run
    ↓
复用 Phase 1 的 run / trajectory / eval 落盘
    ↓
按 task / variant / skill 聚合
    ↓
输出 benchmark results / skill matrix / routing report
    ↓
前端 Evaluation 面板展示
```

关键设计原则：

- **任务优先**：先定义任务，再扩展评分
- **Skill 优先**：先把 Skills Eval 做透，再扩展 Agent Eval
- **固定对照**：Skill 的好坏必须在固定 Agent / 固定模型 / 固定任务下比较
- **结果与过程并重**：既看最终结果，也看 trajectory 和工具路径
- **本地优先**：先做本地薄 Harness，不引入外部依赖
- **可重放**：同一任务、同一变体必须可重复执行

## 8. 任务集设计

### 8.1 第一版任务集原则

第一版任务集不追求大而全，只追求：

- 稳定
- 固定
- 可重复
- 能明显体现 Skill 差异

### 8.2 第一版任务分组建议

#### A. CSV Skill Uplift 组

- `csv_analysis_clean_general`
- `csv_analysis_clean_financial`
- `csv_analysis_dirty_headers`
- `csv_analysis_large_csv`
- `csv_analysis_missing_financial_columns`（第二批增强）
- `csv_analysis_followup`（第二批增强）

关注：

- 是否自动开始全量分析，而不是反问用户
- 是否采用 skill 推荐的 `Read -> Read参考代码 -> Write -> Bash -> UI` 路径
- 是否输出结构化 JSON，而不是直接拼展示文本
- 在财务模式下是否应用 weighted ratio 等领域规则
- 在轻度脏表头、大文件、缺列场景下是否仍然稳健

#### CSV 首批任务包建议

##### 1. `csv_analysis_clean_general`

- 定位：非财务、干净、标准 tabular CSV
- 目的：验证 skill 是否在最基础场景中稳定带来“自动全量分析”能力
- 第一批状态：必做

##### 2. `csv_analysis_clean_financial`

- 定位：标准财务 / 销售型 CSV，具备 `revenue/sales`、`profit/gross_profit`、`year/month`、`product/category`
- 目的：验证 financial enhanced mode 是否真正生效
- 第一批状态：必做

##### 3. `csv_analysis_dirty_headers`

- 定位：轻度脏表头或异名列，如 `Sales Amount`、`Gross Profit`、`Product Line`
- 目的：验证 skill 在“仍可解析但不标准”的现实数据上是否仍有 uplift
- 第一批状态：必做

##### 4. `csv_analysis_large_csv`

- 定位：更大规模的 CSV 文件
- 目的：验证 skill 在大文件场景下是否仍能稳定驱动脚本化分析流程，而不是退化成口头总结
- 第一批状态：必做

##### 5. `csv_analysis_missing_financial_columns`

- 定位：检测到财务语义，但缺少 `revenue` 或 `profit` 关键列
- 目的：验证 skill 是否给出正确 warning / health check，而不是误算
- 第一批状态：第二批增强

##### 6. `csv_analysis_followup`

- 定位：在首次分析结果基础上的继续追问
- 目的：验证 skill 在多轮上下文中的一致性与延续性
- 第一批状态：第二批增强

#### B. Finance Skill Uplift 组

- `finance_cli_aip_basic`
- `finance_cli_years_to_target`
- `finance_cli_mdd_basic`
- `finance_tier2_multi_rate_compare`
- `finance_tier_boundary_cli_vs_code`（第二批增强）
- `finance_compare_lump_vs_aip`（第二批增强）

关注：

- 是否正确激活 `fin-advisor-math`
- 是否正确区分 Tier 1 与 Tier 2
- CLI 能覆盖时是否直接调用 CLI，而不是多写脚本
- CLI 不能覆盖时是否 Read 源码、Write 编排脚本并 import 已有函数
- 是否携带风险提示
- 对比分析时是否遵守参考文档中的输出规范

#### Finance 首批任务包建议

##### 1. `finance_cli_aip_basic`

- 定位：标准定投终值计算
- 目的：验证最典型 Tier 1 CLI 场景
- 第一批状态：必做

##### 2. `finance_cli_years_to_target`

- 定位：从本金推导达到目标金额所需年数
- 目的：验证另一类典型 Tier 1 问题，避免只测单一公式
- 第一批状态：必做

##### 3. `finance_cli_mdd_basic`

- 定位：净值序列型风险指标计算
- 目的：验证 skill 不只是时间价值计算，也覆盖风险指标
- 第一批状态：必做

##### 4. `finance_tier2_multi_rate_compare`

- 定位：多收益率方案比较，CLI 单次 type 难以直接覆盖
- 目的：验证 Tier 2 场景下是否按规范做“编排代码”，并 import 已有函数完成核心计算
- 第一批状态：必做

##### 5. `finance_tier_boundary_cli_vs_code`

- 定位：CLI 理论可覆盖，但问题表述更复杂的边界样本
- 目的：专门测 Tier 1 / Tier 2 判定是否过度工程化
- 第一批状态：第二批增强

##### 6. `finance_compare_lump_vs_aip`

- 定位：一次性投资 vs 定投的对比型问题
- 目的：验证 skill 不只会算单值，也能按参考规范组织对比结论
- 第一批状态：第二批增强

#### C. Routing 组

- `skill_activation_csv`
- `skill_activation_finance`
- `no_skill_needed_general_summary`
- `skill_confusion_nearby_case`

关注：

- 是否漏触发
- 是否误触发
- 是否激活错误 Skill

### 8.2.1 关于 `csv-data-summarizer` 的历史漂移处理策略

当前 `csv-data-summarizer` 存在轻微历史漂移：

- `SKILL.md` 与 `analyze.py` 已经明确约定“只做计算，不直接生成图像或 chart config”
- 但 `resources/README.md` 和 `requirements.txt` 中仍保留了旧的 plotting 相关痕迹

当前建议策略：

- **先不优先修漂移**
- **先把 benchmark 跑起来**
- **评估口径以 `SKILL.md + analyze.py` 为准**
- `resources/README.md` 与 `requirements.txt` 中的历史内容不作为 `Phase A` 评分依据

原因：

- 当前 `Phase 2` 的主目标是先建立 Skills Eval 闭环
- 漂移问题更适合在 benchmark 跑通后，再基于失败案例做定向修复
- 如果现在就先修 skill，本轮 benchmark 的 baseline 反而会被不断移动

### 8.2.2 Fixture 粗粒度对齐原则

对于 `csv_analysis_clean_general` 与 `csv_analysis_clean_financial`：

- 不需要强行做到完全同构
- 但建议在粗粒度难度上保持接近

建议尽量对齐的维度：

- 行数规模
- 列数规模
- 文件大小量级
- 是否都需要脚本化分析而非纯口头总结

不需要强行对齐的维度：

- 业务语义
- 是否财务数据
- 列名体系
- 是否触发 financial enhanced mode

当前建议：

- `clean general` 与 `clean financial` 在规模量级上接近
- `dirty headers` 基于 `financial clean` 派生
- `large csv` 基于 `financial clean` 放大生成

### 8.3 任务定义结构

继续使用 JSON，并在 `Phase 1` 任务定义基础上扩展。

建议字段：

```json
{
  "task_id": "csv_analysis_basic",
  "group": "csv_uplift",
  "description": "标准 CSV 分析任务",
  "input": {
    "user_query": "分析我上传的 csv",
    "session_setup": {
      "uploads": ["fixtures/csv/basic_sales.csv"]
    }
  },
  "variants": ["no_skill", "with_skill", "skill_v1", "skill_v2"],
  "target_skills": ["csv-data-summarizer"],
  "expected_signals": [
    "tool:Read:/workspace/uploads/",
    "client_tool:render_chart|render_table"
  ],
  "expected_artifacts": [],
  "pass_criteria": {
    "final_response_non_empty": true,
    "tool_errors_max": 0,
    "iterations_max": 12
  },
  "scoring_weights": {
    "task_success": 0.35,
    "tool_efficiency": 0.20,
    "artifact_completeness": 0.15,
    "trajectory_quality": 0.30
  }
}
```

### 8.4 fixture 管理

建议结构：

```text
evaluations/
  tasks/
  fixtures/
    csv/
    finance/
```

原则：

- benchmark 输入必须固定
- demo 文件与 benchmark fixture 分离
- benchmark 任务不依赖手工上传

### 8.5 task schema 的参数口径

为避免第一版 schema 失控，当前约定如下：

- `tool_errors_max`：优先采用全局默认值，普通 `uplift` / `routing` task 默认 `0`
- `iterations_max`：优先采用全局默认值，普通 `uplift` task 默认 `12`
- `scoring_weights`：优先按 `eval_type` 提供默认模板，再允许 task 级 override

其中最重要的原则是：

- 不把所有 task 都变成一组独立超参数实验
- 先保证同类任务之间可比
- 第一轮 benchmark 跑完后，再按真实分布回调阈值

## 9. Runner 与 Harness 设计

### 9.1 Runner 的职责

本地 runner 的职责应该是：

- 读取 task 定义
- 准备 session fixture
- 应用 variant 条件
- 触发 agent 运行
- 等待 run 完成
- 读取 run / trajectory / eval / artifacts
- 执行 grader
- 聚合 benchmark 结果
- 写回 benchmark 文件

### 9.2 最小命令形态

第一版只需要本地 CLI，不需要服务化。

建议命令：

```text
python -m agent_system.evaluation.runner --task csv_analysis_basic
python -m agent_system.evaluation.runner --group csv_uplift
python -m agent_system.evaluation.runner --all
python -m agent_system.evaluation.runner --task csv_analysis_basic --variant no_skill
python -m agent_system.evaluation.runner --task csv_analysis_basic --variant skill_v2
```

### 9.3 推荐模块

建议新增：

```text
agent_system/evaluation/
  task_loader.py
  variant_manager.py
  runner.py
  benchmark_store.py
  comparator.py
  routing_metrics.py
```

职责建议：

- `task_loader.py`
  - 读取与校验 task definitions
- `variant_manager.py`
  - 应用 `no_skill / with_skill / skill_v1 / skill_v2`
- `runner.py`
  - 执行 benchmark run
- `benchmark_store.py`
  - 保存 benchmark 聚合结果
- `comparator.py`
  - 计算 uplift、delta、matrix
- `routing_metrics.py`
  - 计算 precision / recall / F1 等 routing 指标

### 9.3.1 Variant Schema 原则

`variant schema` 应单独存在，不建议散落在 task 或 runner 逻辑中。

它的职责应限定为：

- 控制 skill 是否启用
- 控制启用哪些 skill
- 控制 skill 版本
- 控制是否允许 routing

第一版不建议让 variant 直接控制：

- 模型
- prompt
- memory 策略
- 工具白名单

因为 `Phase 2` 当前要回答的问题是：

- 在固定 Agent / 固定模型 / 固定任务下，skill 条件变化是否带来表现差异

### 9.3.2 第一版标准变体

建议标准化以下变体：

- `no_skill`
  - 全部 skill 关闭
- `with_skill`
  - 启用目标 skill 当前主版本
- `skill_v1`
  - 启用目标 skill 的 v1
- `skill_v2`
  - 启用目标 skill 的 v2
- `irrelevant_skill`
  - 启用与当前 task 不相关的 skill

其中：

- `no_skill / with_skill / skill_v1 / skill_v2` 为第一版必做
- `irrelevant_skill` 为建议预留、可第二批实现

### 9.4 结果落盘建议

建议目录：

```text
evaluations/
  benchmarks/
    runs/
    skill_benchmarks/
    routing/
```

其中：

- `benchmarks/runs/*.json`
  - 一次批量回放的完整结果
- `skill_benchmarks/*.json`
  - 某个 Skill 的长期聚合视图
- `routing/*.json`
  - Skill 路由相关指标

## 10. 评分体系增强

### 10.1 当前已有能力

`Phase 1` 已经具备：

- `task_success`
- `tool_efficiency`
- `artifact_completeness`
- `trajectory_quality`

### 10.2 `Phase 2` 需要增强的能力

#### A. `expected_signals` 匹配

支持判断：

- 是否出现特定工具
- 是否访问特定路径
- 是否发出特定客户端工具
- 是否发生特定 skill 注入

例如：

- `tool:Read:/workspace/uploads/`
- `client_tool:render_chart|render_table`
- `skill:csv-data-summarizer`

第一版原则：

- `expected_signals` 只用于表达高信号证据
- 不做严格工具顺序匹配
- 不做参数完全匹配
- 不做精确次数匹配
- 不把它设计成唯一正确轨迹模板

#### B. `expected_artifacts` 匹配

检查：

- `temp/*.py`
- `.tool-results/*.txt`
- `output/*.html`

第一版原则：

- 优先依赖 recorder 能稳定记录的产物
- `Write` 直接创建的文件和 `.tool-results/*.txt` 是最可靠的两类
- 通过 `Bash` 间接产生的文件不建议在第一版作为强校验项，除非补充更强的文件系统扫描能力

#### C. `pass_criteria` 绑定

支持：

- 最大工具错误数
- 最大迭代数
- 是否必须有最终回答

#### D. Variant 对照聚合

支持自动生成：

- `baseline_avg`
- `skill_avg`
- `lift`
- `negative_delta`

#### E. Routing 指标

支持：

- `activation_precision`
- `activation_recall`
- `activation_f1`

### 10.3 评分项职责边界

第一版建议使用以下口径：

- `task_success`
  - 只回答“任务是否完成”
- `signal_match`
  - 只回答“关键高信号行为是否出现”
- `artifact_match`
  - 只回答“预期产物是否存在”
- `tool_efficiency`
  - 只回答“工具使用成本与浪费程度”
- `trajectory_quality`
  - 只回答“过程是否稳定、收敛、没有明显异常折返”

其中，`trajectory_quality` 明确不负责：

- 不直接评最终任务是否完成
- 不评 task-specific 信号是否命中
- 不评产物是否存在
- 不评固定工具顺序

`trajectory_quality` 在 `Phase 2 v1` 中建议定义为：

- 对通用异常轨迹模式的惩罚分

第一版先基于：

- `status`
- `tool_errors`
- `iterations`

后续再逐步扩展到：

- 重复 skill 注入
- 连续同类工具失败
- 同路径重复读写
- 无推进空转轮次

## 11. 前端与接口方向

### 11.1 前端展示目标

`Evaluation` 面板内部建议拆成三层：

- 最近运行
- Task Benchmark
- Skill Benchmark

在 `Phase B` 后再增加：

- Skill Routing

### 11.2 后端接口方向

建议逐步新增：

- `GET /evaluation/tasks/{task_id}`
- `GET /evaluation/tasks/{task_id}/runs`
- `GET /evaluation/benchmarks`
- `GET /evaluation/benchmarks/{benchmark_id}`
- `GET /evaluation/skill-benchmarks`
- `GET /evaluation/skill-benchmarks/{skill_name}`
- `GET /evaluation/skill-routing/{skill_name}`

本阶段仍然不需要：

- benchmark 写接口
- 在线标注接口
- 外部平台同步接口

CLI runner 写文件即可。

## 12. 实施顺序

### Step 1：任务定义扩展

先做：

- 扩展 `evaluations/tasks/*.json`
- 补 `fixtures/`
- 明确 task schema
- 明确 variant schema

### Step 2：评分增强

扩展：

- `agent_system/evaluation/scorer.py`

支持：

- `expected_signals`
- `expected_artifacts`
- `pass_criteria`
- task-level 权重

### Step 3：Phase A Runner

新增：

- `task_loader.py`
- `variant_manager.py`
- `runner.py`
- `benchmark_store.py`
- `comparator.py`

先保证本地 CLI 能跑通 Skills Uplift Eval。

### Step 4：Skill Benchmark 聚合

生成：

- benchmark run JSON
- skill benchmark JSON
- skill matrix

### Step 5：Phase B Routing

新增：

- routing 任务组
- `routing_metrics.py`
- precision / recall / F1 聚合

### Step 6：查询接口与前端视图

最后做：

- benchmark list / detail
- skill benchmark detail
- routing 视图
- `EvaluationPanel` 升级

## 13. 验收标准

完成 `Phase 2` 后，至少满足：

1. `evaluations/tasks/` 中至少有 5 个稳定任务
2. 本地 runner 能按 task / group / all 执行 benchmark
3. 至少支持 `no_skill / with_skill / skill_v1 / skill_v2`
4. benchmark 结果能落盘
5. skill benchmark matrix 能生成
6. 每个 benchmark 结果都能追溯到具体 run
7. `Evaluation` 面板能看到 benchmark 与 skill 对比
8. 整套流程不依赖任何外部 eval 平台

## 14. 风险与注意事项

### 14.1 不要先做泛化 Agent 大评测

当前阶段最容易犯的错误，就是在没有明确场景的前提下过早铺开通用 Agent Eval。  
这样很容易得到“看起来很完整、但不指导优化”的分数。

### 14.2 不要把 Skill Eval 做成文档评审

Skill 的价值必须通过任务表现验证，而不是靠人工读 `SKILL.md` 给主观评价。

### 14.3 不要过早引入平台

`Harbor / Braintrust / Phoenix / LangSmith / Langfuse` 都可以后续接，但现在不是最该先解决的问题。  
现在最缺的是任务、变体、grader 和聚合逻辑。

### 14.4 不要让 task schema 过度自由

Schema 越自由，后续评分和比较越容易失控。  
`Phase 2` 追求的是“够用且统一”，不是“表达一切”。

### 14.5 不要过早做复杂 DSL

`expected_signals` 第一版可以先用简单字符串约定。  
不要一开始就发明复杂表达式语言。

## 15. 与后续 Phase 3 的衔接

`Phase 2` 做完后，项目应具备：

- 固定任务集
- Skills Eval Harness
- benchmark runner
- skill benchmark matrix
- routing 指标
- 本地可比较基线

这时再接外部平台才是合理顺序。

也就是说：

- `Phase 1` 提供 run 事实层
- `Phase 2` 提供 Skills Eval 与 benchmark 比较层
- `Phase 3` 再考虑外部实验平台和更完整的 Agent Eval

这是当前项目最稳的演进路径。
