# System Architecture Overview

## Product Shape

当前系统已经从早期 `Claude Skills Lab` 演进为 `Skill Eval Studio`。核心目标不是做一个通用聊天 Demo，而是验证和迭代可插拔 skills 对 Agent 表现的增益。

一等对象：

- `skill`
- `benchmark`
- `variant`
- `run`
- `comparison`

`session`、`trajectory`、`artifact` 是 Debug Lab 和底层追溯对象，不作为产品主导航的一等评测对象。

## Runtime Components

| 模块 | 职责 |
| --- | --- |
| `agent_system/agent/` | Agent 主循环、提示词、记忆压缩、run 生命周期收口 |
| `agent_system/tools/` | Read / Write / List / Bash / Skill 等工具适配 |
| `agent_system/skills/` | 扫描 `skills/*/SKILL.md`，按元数据暴露 skill |
| `agent_system/evaluation/` | run 记录、task loader、variant、scorer、benchmark、comparator |
| `server/` | FastAPI API、workspace、run/eval 查询、CopilotKit SSE 适配 |
| `frontend/` | React Debug Lab、Workspace、Trajectory、Evaluation 面板 |
| `docker-sandbox/` | MCP 沙箱服务，承载受限文件和 Python 执行能力 |

## Core Flow

```text
User / Benchmark
  -> FastAPI / Copilot adapter
  -> Agent
  -> SkillManager + ToolRegistry
  -> Read / Write / List / Bash / Skill
  -> RunRecorder
  -> run.json / trajectory.jsonl / artifacts.json / eval.json
  -> Debug Lab / Evaluation views
```

## Tool Model

当前基座坚持“原子工具 + skills”：

- `Read`：读取文件，带分页和截断保护。
- `Write`：写文件，动态代码必须先落盘。
- `List`：列目录和发现文件。
- `Bash`：只执行 Python 脚本，不做通用 shell。
- `Skill`：把匹配的 skill 内容注入上下文。
- UI tools：`render_chart` / `render_table` / `show_notification` 在前端渲染。

## Current Constraint

新增能力优先落在 skill 或 eval task 中。只有当能力跨多个业务场景稳定复用，且现有原子工具组合成本过高时，才考虑新增底层工具。
