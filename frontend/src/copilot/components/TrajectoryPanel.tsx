/**
 * TrajectoryPanel - 运行轨迹面板
 *
 * 展示当前 session 最近一次 run 的摘要与时间线。
 * 包含三个区域：运行摘要卡片、时间线、证据文件快捷入口。
 */
import { Activity, AlertCircle, CheckCircle2, Clock, FileText, Hash, Loader2, Wrench, XCircle } from "lucide-react";
import { useMemo } from "react";

import type { ArtifactsRecord, EvalRecord, RunRecord, TrajectoryEvent } from "../../types";

interface TrajectoryPanelProps {
  run: RunRecord | null;
  trajectory: TrajectoryEvent[];
  evalResult: EvalRecord | null;
  artifacts?: ArtifactsRecord | null;
  loading: boolean;
  onOpenFile?: (path: string) => void;
}

function StatusBadge({ status }: { status: string }) {
  const passed = status === "passed";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        padding: "4px 10px",
        borderRadius: "999px",
        fontSize: "11px",
        fontWeight: 600,
        background: passed ? "rgba(59, 162, 114, 0.15)" : "rgba(255, 100, 100, 0.15)",
        color: passed ? "#59dba2" : "#ff8a8a",
        border: `1px solid ${passed ? "rgba(59, 162, 114, 0.3)" : "rgba(255, 100, 100, 0.3)"}`,
      }}
    >
      {passed ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
      {passed ? "成功" : "失败"}
    </span>
  );
}

function formatDuration(ms: number | null | undefined): string {
  if (!ms) return "-";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("zh-CN", { hour12: false });
  } catch {
    return iso;
  }
}

const EVENT_LABELS: Record<string, string> = {
  run_started: "运行开始",
  iteration_started: "迭代开始",
  llm_call_started: "LLM 调用",
  llm_call_finished: "LLM 完成",
  thinking: "思考",
  tool_call_started: "工具调用",
  tool_call_finished: "工具完成",
  skill_injected: "技能注入",
  artifact_created: "产物创建",
  client_tool_emitted: "客户端工具",
  run_completed: "运行完成",
  run_failed: "运行失败",
};

const EVENT_COLORS: Record<string, string> = {
  run_started: "#76a5ff",
  iteration_started: "#76a5ff",
  llm_call_started: "#c4b5fd",
  llm_call_finished: "#c4b5fd",
  thinking: "#fbbf24",
  tool_call_started: "#34d399",
  tool_call_finished: "#34d399",
  skill_injected: "#f472b6",
  artifact_created: "#60a5fa",
  client_tool_emitted: "#a78bfa",
  run_completed: "#59dba2",
  run_failed: "#ff8a8a",
};

function ScoreBar({ label, value }: { label: string; value: number | null }) {
  if (value === null || value === undefined) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "12px" }}>
        <span style={{ width: "100px", color: "rgba(255,255,255,0.6)" }}>{label}</span>
        <span style={{ color: "rgba(255,255,255,0.35)" }}>N/A</span>
      </div>
    );
  }
  const pct = Math.round(value * 100);
  const barColor = pct >= 80 ? "#59dba2" : pct >= 50 ? "#fbbf24" : "#ff8a8a";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "12px" }}>
      <span style={{ width: "100px", color: "rgba(255,255,255,0.6)", flexShrink: 0 }}>{label}</span>
      <div
        style={{
          flex: 1,
          height: "6px",
          borderRadius: "3px",
          background: "rgba(255,255,255,0.08)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            borderRadius: "3px",
            background: barColor,
            transition: "width 0.4s ease",
          }}
        />
      </div>
      <span style={{ width: "36px", textAlign: "right", color: "rgba(255,255,255,0.7)", flexShrink: 0 }}>{pct}%</span>
    </div>
  );
}

export function TrajectoryPanel({ run, trajectory, evalResult, artifacts, loading, onOpenFile }: TrajectoryPanelProps) {
  const visibleEvents = useMemo(
    () => trajectory.filter((e) => !["run_started", "llm_call_started"].includes(e.type)),
    [trajectory]
  );

  const artifactPaths = useMemo(() => {
    if (artifacts?.files?.length) {
      return artifacts.files;
    }
    return [...new Set(trajectory.filter((e) => e.type === "artifact_created" && e.path).map((e) => e.path as string))];
  }, [artifacts, trajectory]);

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "24px", color: "rgba(255,255,255,0.55)" }}>
        <Loader2 size={16} style={{ animation: "spin 1s linear infinite" }} />
        正在加载运行数据...
      </div>
    );
  }

  if (!run) {
    return (
      <div style={{ padding: "24px", color: "rgba(255,255,255,0.45)", lineHeight: 1.7 }}>
        <Activity size={28} style={{ marginBottom: "12px", opacity: 0.4 }} />
        <div>当前会话暂无运行记录。</div>
        <div style={{ fontSize: "12px", marginTop: "6px" }}>发送一条消息后，这里会展示本次运行的轨迹与评估。</div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px", padding: "12px 0" }}>
      {/* 运行摘要卡片 */}
      <div
        style={{
          padding: "14px 16px",
          borderRadius: "16px",
          background: "rgba(255,255,255,0.04)",
          border: "1px solid rgba(255,255,255,0.08)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "10px" }}>
          <span style={{ fontSize: "13px", fontWeight: 600, color: "#f4f7ff" }}>
            {run.run_id.slice(0, 24)}
          </span>
          <StatusBadge status={run.status} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 16px", fontSize: "12px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "rgba(255,255,255,0.6)" }}>
            <Clock size={12} /> {formatDuration(run.duration_ms)}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "rgba(255,255,255,0.6)" }}>
            <Hash size={12} /> {run.iterations} 轮
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "rgba(255,255,255,0.6)" }}>
            <Wrench size={12} /> {run.tool_calls} 次工具
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "6px", color: run.tool_errors > 0 ? "#ff8a8a" : "rgba(255,255,255,0.6)" }}>
            <AlertCircle size={12} /> {run.tool_errors} 次错误
          </div>
        </div>
        {run.task_id !== "adhoc" ? (
          <div style={{ marginTop: "8px", fontSize: "11px", color: "rgba(255,255,255,0.45)" }}>
            任务: {run.task_id}
          </div>
        ) : null}
      </div>

      {/* 评分条 */}
      {evalResult?.scores ? (
        <div
          style={{
            padding: "12px 16px",
            borderRadius: "16px",
            background: "rgba(255,255,255,0.03)",
            border: "1px solid rgba(255,255,255,0.06)",
            display: "flex",
            flexDirection: "column",
            gap: "8px",
          }}
        >
          <div style={{ fontSize: "12px", fontWeight: 600, color: "rgba(255,255,255,0.5)", marginBottom: "2px" }}>
            评分
          </div>
          <ScoreBar label="任务成功" value={evalResult.scores.task_success} />
          <ScoreBar label="工具效率" value={evalResult.scores.tool_efficiency} />
          <ScoreBar label="产物完整" value={evalResult.scores.artifact_completeness} />
          <ScoreBar label="轨迹质量" value={evalResult.scores.trajectory_quality} />
        </div>
      ) : null}

      {/* 时间线 */}
      {visibleEvents.length > 0 ? (
        <div>
          <div style={{ fontSize: "12px", fontWeight: 600, color: "rgba(255,255,255,0.5)", marginBottom: "8px", paddingLeft: "4px" }}>
            时间线 ({visibleEvents.length} 事件)
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
            {visibleEvents.map((event, i) => {
              const color = EVENT_COLORS[event.type] || "#76a5ff";
              const label = EVENT_LABELS[event.type] || event.type;
              let detail = "";
              if (event.tool_name) detail = event.tool_name;
              else if (event.message) detail = event.message.slice(0, 60);
              else if (event.path) detail = event.path;
              else if (event.skills?.length) detail = event.skills.join(", ");

              return (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: "10px",
                    padding: "6px 8px",
                    borderRadius: "8px",
                    fontSize: "11px",
                    lineHeight: 1.5,
                  }}
                >
                  <div
                    style={{
                      width: "8px",
                      height: "8px",
                      borderRadius: "50%",
                      background: color,
                      flexShrink: 0,
                      marginTop: "4px",
                    }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ color, fontWeight: 600 }}>{label}</span>
                    {detail ? (
                      <span style={{ color: "rgba(255,255,255,0.5)", marginLeft: "6px" }}>
                        {detail}
                      </span>
                    ) : null}
                    {event.duration_ms ? (
                      <span style={{ color: "rgba(255,255,255,0.35)", marginLeft: "6px" }}>
                        {formatDuration(event.duration_ms)}
                      </span>
                    ) : null}
                    {event.error ? (
                      <div style={{ color: "#ff8a8a", marginTop: "2px" }}>{event.error.slice(0, 100)}</div>
                    ) : null}
                  </div>
                  <span style={{ color: "rgba(255,255,255,0.3)", flexShrink: 0, fontSize: "10px" }}>
                    {formatTime(event.timestamp)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {/* 证据文件快捷入口 */}
      {artifactPaths.length > 0 ? (
        <div>
          <div style={{ fontSize: "12px", fontWeight: 600, color: "rgba(255,255,255,0.5)", marginBottom: "8px", paddingLeft: "4px" }}>
            产物文件 ({artifactPaths.length})
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            {artifactPaths.map((p) => {
              const filename = p.split("/").pop() || p;
              return (
                <button
                  type="button"
                  key={p}
                  onClick={() => onOpenFile?.(p)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    padding: "6px 10px",
                    borderRadius: "8px",
                    border: "1px solid rgba(255,255,255,0.08)",
                    background: "rgba(255,255,255,0.03)",
                    color: "#76a5ff",
                    fontSize: "12px",
                    cursor: "pointer",
                    textAlign: "left",
                    width: "100%",
                  }}
                  title={p}
                >
                  <FileText size={13} style={{ flexShrink: 0 }} />
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{filename}</span>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default TrajectoryPanel;
