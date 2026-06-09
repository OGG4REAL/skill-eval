# Architecture Decision Records

本文件记录当前项目的关键决策路线。它不是变更日志，只记录会影响后续实现取舍的“为什么”。

## ADR-001: 冻结内存执行，采用 Write + Bash

- 日期：2026-01
- 状态：已实施
- 背景：内存 REPL / `run_python_code` 无法审计执行代码，也容易绕过 skill 里的可复用脚本和规范。
- 决策：动态代码必须先写入文件，再通过 `Bash` 执行 Python 脚本。
- 后果：所有计算过程有文件留痕；复杂任务多一步写文件，但符合银行场景的可追溯要求。

## ADR-002: 工具层采用原子工具

- 日期：2026-02
- 状态：已实施
- 背景：用 Bash 兼做读写、列目录和执行会造成职责重叠，也不利于限制权限。
- 决策：文件操作走 `Read` / `Write` / `List`，执行只走 `Bash`，skill 注入走 `Skill`。
- 后果：工具职责更清楚，前后端和 Docker MCP 层更容易审计；新增工具必须先证明是跨场景原子能力。

## ADR-003: Bash 只允许执行 Python 脚本

- 日期：2026-02
- 状态：已实施
- 背景：文件操作已有原子工具覆盖后，Bash 不再需要承担 shell 探索职责。
- 决策：Bash 白名单收敛到 `python` / `python3` 脚本执行，禁止管道、重定向、危险命令和内联执行。
- 后果：安全边界更窄；Agent 需要通过 `Write` 留下脚本，再执行脚本。

## ADR-004: `csv-data-summarizer` 采用代码模板模式

- 日期：2026-02
- 状态：已实施
- 背景：CSV 分析的数据列和业务问题在运行前不可预知，固定 CLI 很难覆盖。
- 决策：`csv-data-summarizer` 的参考代码作为模板和模式来源，Agent 读取后为当前数据写定制脚本。
- 后果：灵活性高于固定 CLI；结果质量需要通过 eval harness 回归验证。

## ADR-005: Phase 2 先做本地 Skills Eval Harness

- 日期：2026-03
- 状态：已实施主链路
- 背景：通用 Agent Benchmark 没有稳定任务族时难以指导优化，但 skills 是当前系统的核心资产。
- 决策：Phase 2 主线收敛为本地 `Skills Eval Harness`，先比较 `no_skill` / `with_skill` 的表现变化。
- 后果：先得到可重复的 skill uplift 证据；外部平台、LLM judge、人工标注和复杂 DSL 后置。

## ADR-006: Trajectory 是证据，不是评分主线

- 日期：2026-04
- 状态：已采纳
- 背景：只看工具调用路径会高估“过程像不像”，但无法证明结果正确。
- 决策：评分主线从 trajectory-first 转到 result-first verifier / rubric；trajectory 保留为 Debug Lab 证据。
- 后果：`phase2-12` 优先实现结果校验，routing 和继续扩 task 暂时后置。

## ADR-007: ADR 用单文件维护

- 日期：2026-05-18
- 状态：已采纳
- 背景：当前决策数量有限，单独目录会增加文档维护成本。
- 决策：不建 `ADR/` 目录，统一维护 `docs/adr.md`。
- 后果：新增决策继续追加到本文件；只有当决策量显著增加时再重新评估拆分。

## ADR-008: Evaluation API Contract 采用 Store/Comparator Helper

- 日期：2026-05-19
- 状态：已实施
- 背景：Evaluation UI 需要稳定 contract，但直接在 `server/app.py` 拼装会让路由膨胀；新增 service 层又会让 Phase 1 过重。
- 决策：在 `BenchmarkStore` 和 `SkillComparator` 上补 summary / contract helper，FastAPI 只做薄路由、参数校验和错误码映射。
- 后果：前端消费 `/evaluation/*` contract，不读取本地 benchmark JSON；benchmark detail 不透传完整 raw `cases`；同步 benchmark run 暂不扩成 queue / job 系统。
