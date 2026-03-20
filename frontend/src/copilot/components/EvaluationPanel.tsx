/**
 * EvaluationPanel - 评估面板
 *
 * 展示跨 run 的运行列表和基础对比，支持：
 * A. 当前会话最近运行列表
 * B. 全局最近运行列表
 * C. 相邻 run 的 delta 比较
 */
import { BarChart3, CheckCircle2, Clock, Loader2, TrendingDown, TrendingUp, Wrench, XCircle } from "lucide-react";

import type { RunIndexEntry, RunRecord } from "../../types";

interface EvaluationPanelProps {
  sessionRuns: RunRecord[];
  globalRuns: RunIndexEntry[];
  loading: boolean;
  activeRunId: string | null;
  onSelectRun?: (runId: string, sessionId?: string) => void;
}

function formatDuration(ms: number | null | undefined): string {
  if (!ms) return "-";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return iso;
  }
}

function DeltaIndicator({ current, previous, unit, inverse }: {
  current: number | null | undefined;
  previous: number | null | undefined;
  unit?: string;
  inverse?: boolean;
}) {
  if (current == null || previous == null) return null;
  const diff = current - previous;
  if (diff === 0) return null;
  const improved = inverse ? diff < 0 : diff > 0;
  const color = improved ? "#59dba2" : "#ff8a8a";
  const prefix = diff > 0 ? "+" : "";
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "2px", fontSize: "10px", color }}>
      {improved ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
      {prefix}{diff}{unit || ""}
    </span>
  );
}

function RunRow({
  run,
  isActive,
  previousRun,
  onClick,
}: {
  run: RunRecord | RunIndexEntry;
  isActive: boolean;
  previousRun?: RunRecord | RunIndexEntry | null;
  onClick?: () => void;
}) {
  const passed = run.status === "passed";
  const score = "score" in run ? (run as RunIndexEntry).score : null;
  const createdAt = "created_at" in run ? (run as RunIndexEntry).created_at : ("started_at" in run ? (run as RunRecord).started_at : null);

  return (
    <button
      onClick={onClick}
      style={{
        width: "100%",
        display: "flex",
        alignItems: "center",
        gap: "10px",
        padding: "10px 12px",
        borderRadius: "12px",
        border: isActive ? "1px solid rgba(118, 165, 255, 0.3)" : "1px solid rgba(255,255,255,0.06)",
        background: isActive ? "rgba(118, 165, 255, 0.1)" : "rgba(255,255,255,0.02)",
        color: "rgba(255,255,255,0.78)",
        cursor: onClick ? "pointer" : "default",
        textAlign: "left",
        fontSize: "12px",
      }}
    >
      <span style={{ flexShrink: 0, color: passed ? "#59dba2" : "#ff8a8a" }}>
        {passed ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontWeight: 600, color: "#f4f7ff", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {run.task_id === "adhoc" ? "临时任务" : run.task_id}
          </span>
          {score !== null ? (
            <span
              style={{
                padding: "2px 6px",
                borderRadius: "999px",
                fontSize: "10px",
                fontWeight: 700,
                background: score >= 0.8 ? "rgba(59,162,114,0.15)" : score >= 0.5 ? "rgba(251,191,36,0.15)" : "rgba(255,100,100,0.15)",
                color: score >= 0.8 ? "#59dba2" : score >= 0.5 ? "#fbbf24" : "#ff8a8a",
              }}
            >
              {Math.round(score * 100)}
            </span>
          ) : null}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", marginTop: "4px", color: "rgba(255,255,255,0.45)", fontSize: "11px" }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "3px" }}>
            <Clock size={10} /> {formatDuration(run.duration_ms)}
            <DeltaIndicator current={run.duration_ms} previous={previousRun?.duration_ms} unit="ms" inverse />
          </span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "3px" }}>
            <Wrench size={10} /> {run.tool_calls}
            <DeltaIndicator current={run.tool_calls} previous={previousRun?.tool_calls} inverse />
          </span>
          <span>{formatTime(createdAt)}</span>
        </div>
      </div>
    </button>
  );
}

export function EvaluationPanel({
  sessionRuns,
  globalRuns,
  loading,
  activeRunId,
  onSelectRun,
}: EvaluationPanelProps) {
  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "24px", color: "rgba(255,255,255,0.55)" }}>
        <Loader2 size={16} style={{ animation: "spin 1s linear infinite" }} />
        正在加载评估数据...
      </div>
    );
  }

  const hasSessionRuns = sessionRuns.length > 0;
  const hasGlobalRuns = globalRuns.length > 0;

  if (!hasSessionRuns && !hasGlobalRuns) {
    return (
      <div style={{ padding: "24px", color: "rgba(255,255,255,0.45)", lineHeight: 1.7 }}>
        <BarChart3 size={28} style={{ marginBottom: "12px", opacity: 0.4 }} />
        <div>暂无评估数据。</div>
        <div style={{ fontSize: "12px", marginTop: "6px" }}>完成至少一次对话后，这里会展示运行列表和评估对比。</div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px", padding: "12px 0" }}>
      {/* 当前会话运行列表 */}
      {hasSessionRuns ? (
        <div>
          <div style={{ fontSize: "12px", fontWeight: 600, color: "rgba(255,255,255,0.5)", marginBottom: "8px", paddingLeft: "4px" }}>
            当前会话 ({sessionRuns.length} 次运行)
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {sessionRuns.map((run, i) => (
              <RunRow
                key={run.run_id}
                run={run}
                isActive={run.run_id === activeRunId}
                previousRun={i < sessionRuns.length - 1 ? sessionRuns[i + 1] : null}
                onClick={onSelectRun ? () => onSelectRun(run.run_id) : undefined}
              />
            ))}
          </div>
        </div>
      ) : null}

      {/* 全局运行列表 */}
      {hasGlobalRuns ? (
        <div>
          <div style={{ fontSize: "12px", fontWeight: 600, color: "rgba(255,255,255,0.5)", marginBottom: "8px", paddingLeft: "4px" }}>
            全局最近运行 ({globalRuns.length})
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {globalRuns.slice(0, 20).map((entry, i) => (
              <RunRow
                key={entry.run_id}
                run={entry}
                isActive={entry.run_id === activeRunId}
                previousRun={i < globalRuns.length - 1 ? globalRuns[i + 1] : null}
                onClick={onSelectRun ? () => onSelectRun(entry.run_id, entry.session_id) : undefined}
              />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default EvaluationPanel;
