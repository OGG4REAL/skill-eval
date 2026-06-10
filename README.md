# Skill Eval Studio

一个本地优先的 skill 评估与复盘工作台，用来回答一个直接问题：

> 某个 skill 到底有没有让 Agent 的任务结果变好？

当前项目已经从早期 Agent Studio / Debug Lab 原型，收敛为面向 skill 的本地 evaluation harness。Debug Lab 仍然保留，用于查看单次 run 的 trajectory、artifact 和 workspace 证据，但最终评分主线以结果校验为准。

## 现在能做什么

- 定义本地 evaluation task，并用 result-first verifier 校验最终结果。
- 运行 benchmark，对比 `no_skill` / `with_skill`。
- 对比 `skill_v1` / `skill_v2`。
- 检查 irrelevant skill 误触发。
- 在前端 Skill Eval 面板里选择 task、上传 task JSON、发起评估并查看结果。
- 查看 result score、result pass rate、normalized gain、失败样本和 Debug Lab run 引用。
- 通过 Debug Lab 复盘单次 run 的 trajectory、输出 artifact 和 workspace 文件。

## 不做什么

当前阶段不做：

- 通用 Agent benchmark 平台
- 外部 eval 平台对接
- 云端 experiment 管理
- 后台 job queue / 异步轮询
- LLM judge
- 人工审核后台
- 多模型 leaderboard
- 多租户权限模型

这些不是技术上不能做，而是为了让 side project 保持小、直接、可维护。

## 项目结构

```text
agent_system/
  agent/                  # Agent 主循环、LLM client、prompt
  evaluation/             # BenchmarkRunner、TaskLoader、SkillComparator、RunRecorder 等
  tools/                  # 文件、Bash、MCP 工具适配
docker-sandbox/           # MCP sandbox server
evaluations/
  tasks/                  # 本地 eval task JSON
  benchmarks/runs/        # benchmark 结果 JSON
frontend/                 # React + Vite 前端
server/                   # FastAPI API server
skills/                   # 被评估的 skills
tests/                    # 后端 contract、runner、comparator、regression 测试
docs/                     # 产品、架构、roadmap 和 phase 文档
```

## 快速启动

### 1. 安装依赖

Windows / PowerShell 下建议先使用 `.venv`：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-agent.txt

cd frontend
npm install
cd ..
```

复制环境变量模板：

```powershell
Copy-Item env.example .env
```

然后在 `.env` 里配置你的模型 API key，例如 `DEEPSEEK_API_KEY`。

### 2. 启动后端

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn server.app:app --host 127.0.0.1 --port 8001 --reload
```

后端默认 API 地址：`http://127.0.0.1:8001`

### 3. 启动前端

另开一个 PowerShell：

```powershell
cd frontend
npm run dev
```

前端默认地址：`http://127.0.0.1:5173`

打开页面后，在右侧面板切到 **Skill Eval**。

## 前端评估流程

Skill Eval 面板默认只暴露三个用户概念：

1. **这个 skill 有没有帮助**
   - 内部对比：`no_skill` vs `with_skill`

2. **两个版本哪个更好**
   - 内部对比：`skill_v1` vs `skill_v2`

3. **会不会误触发**
   - 内部对比：`no_skill` vs `irrelevant_skill`

推荐流程：

1. 选择评估模式。
2. 选择已有 task，或上传一个 task JSON。
3. 点击 **开始评估**。
4. 跑完后查看 result uplift、normalized gain、失败样本。
5. 需要排查时，点击 failed case / run ref 跳到 Debug Lab。

`variant`、`group`、`benchmark_id`、weighted score 等工程细节默认放在高级详情里。

## Task JSON

本地 task 放在：

```text
evaluations/tasks/*.json
```

前端上传 task 时会调用：

```http
POST /evaluation/tasks/import
```

导入规则：

- 顶层必须是 JSON object。
- 使用 `TaskLoader` 做 schema 校验。
- 默认不覆盖同名 task。
- 返回精简 task 摘要，不暴露本地文件路径。

运行 benchmark 时调用：

```http
POST /evaluation/benchmarks/run
```

后端同步运行现有 `BenchmarkRunner`，不引入数据库、不引入后台队列。

## 主要 API

Evaluation API contract：

```text
GET  /evaluation/overview
GET  /evaluation/benchmarks
GET  /evaluation/benchmarks/{benchmark_id}
GET  /evaluation/skills/{skill}/summary
GET  /evaluation/comparisons
GET  /evaluation/tasks
POST /evaluation/tasks/import
POST /evaluation/benchmarks/run
```

兼容旧 Debug Lab / run 查看入口：

```text
GET /evaluation/runs
GET /sessions/{session_id}/runs
GET /sessions/{session_id}/runs/{run_id}/trajectory
GET /sessions/{session_id}/runs/{run_id}/artifacts
GET /sessions/{session_id}/runs/{run_id}/eval
```

## 测试

后端全量测试：

```powershell
python -m pytest -q
```

前端检查：

```powershell
cd frontend
npm run lint
npm run build
```

本轮基线状态：

- `python -m pytest -q`：527 passed
- `npm run lint`：通过
- `npm run build`：通过

## 关键文档

- [产品方向](docs/products/skill-eval-studio.md)
- [Roadmap](docs/products/roadmap.md)
- [当前状态](docs/skill-eval-restructure/current-state.md)
- [Result-first verifier](docs/skill-eval-restructure/phase2-12-result-first-verifier.md)
- [Evaluation API and UI](docs/skill-eval-restructure/phase2-13-evaluation-api-and-ui.md)
- [Regression and failure cases](docs/skill-eval-restructure/phase2-14-regression-and-failure-cases.md)

## GitHub 留档

当前 GitHub 远端：

```text
ssh://git@ssh.github.com:443/OGG4REAL/skill-eval.git
```

推荐后续每次完成一个可验证小闭环后提交一次，避免把临时 sessions、output、Playwright 快照和本地 transcript 推上去。
