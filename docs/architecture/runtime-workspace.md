# Runtime and Workspace Architecture

## Session Layout

每个 session 是一次可追溯工作区，默认位于 `sessions/{session_id}/`。

```text
sessions/{session_id}/
  uploads/
  output/
  temp/
  .tool-results/
  chat.log
  history.json
  runs/{run_id}/
    run.json
    trajectory.jsonl
    artifacts.json
    eval.json
```

## Logical Workspace

前端和 Agent 看到的是逻辑 `/workspace`：

| 逻辑路径 | 实际来源 | 写权限 |
| --- | --- | --- |
| `/workspace/uploads` | 当前 session uploads | 可写 |
| `/workspace/output` | 当前 session output | 可写 |
| `/workspace/temp` | 当前 session temp | 可写 |
| `/workspace/.tool-results` | 大工具输出落盘目录 | 可写 |
| `/workspace/chat.log` | 当前 session 日志 | 可读 |
| `/workspace/history.json` | 当前 session 历史 | 可读 |
| `/workspace/skills` | 项目 `skills/` | 只读 |

## API Surface

主要后端入口：

- `POST /sessions`
- `GET /sessions`
- `GET /sessions/{session_id}/workspace`
- `GET /sessions/{session_id}/workspace/file?path=...`
- `POST /sessions/{session_id}/files`
- `GET /sessions/{session_id}/files`
- `GET /sessions/{session_id}/outputs`
- `POST /copilotkit/chat`

run 复盘入口：

- `GET /sessions/{session_id}/runs`
- `GET /sessions/{session_id}/runs/{run_id}`
- `GET /sessions/{session_id}/runs/{run_id}/trajectory`
- `GET /sessions/{session_id}/runs/{run_id}/artifacts`
- `GET /sessions/{session_id}/runs/{run_id}/eval`

评估索引入口：

- `GET /evaluation/runs`
- `GET /evaluation/tasks`

## Artifact Tracking

`RunRecorder` 写入 run 事实。Agent 在工具执行前后扫描 `temp`、`output`、`.tool-results`，把新增产物登记到 `artifacts.json`，避免只记录显式 UI artifact 而漏掉 Bash 间接生成文件。

历史 run 不会自动回填新的 artifact 记录；验证 tracing 或 artifact 修复时必须跑新 run。
