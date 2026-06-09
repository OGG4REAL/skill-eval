import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  FileJson,
  GitCompare,
  Loader2,
  MousePointer2,
  Play,
  RefreshCw,
  ShieldAlert,
  SlidersHorizontal,
  TrendingDown,
  TrendingUp,
  Upload,
  XCircle,
} from "lucide-react";

import {
  getEvaluationBenchmark,
  getEvaluationComparisons,
  getEvaluationOverview,
  getEvaluationSkillSummary,
  importEvaluationTask,
  listEvaluationBenchmarks,
  listEvaluationTasks,
  runEvaluationBenchmark,
} from "../../lib/api";
import type {
  EvaluationBenchmarkDetailResponse,
  EvaluationBenchmarkFailedCase,
  EvaluationBenchmarkListItem,
  EvaluationBenchmarkMatrixRow,
  EvaluationComparisonResponse,
  EvaluationOverviewResponse,
  EvaluationSkillSummaryResponse,
  EvaluationTaskDefinition,
  EvaluationTaskSummary,
  RunIndexEntry,
  RunRecord,
} from "../../types";

interface EvaluationPanelProps {
  sessionRuns: RunRecord[];
  globalRuns: RunIndexEntry[];
  loading: boolean;
  activeRunId: string | null;
  onSelectRun?: (runId: string, sessionId?: string) => void;
}

type EvalModeId = "effect" | "version" | "misfire";

type EvalMode = {
  id: EvalModeId;
  title: string;
  description: string;
  baselineVariant: string;
  targetVariant: string;
  icon: ReactNode;
};

type LoadState = {
  overview: EvaluationOverviewResponse | null;
  benchmarks: EvaluationBenchmarkListItem[];
  tasks: EvaluationTaskSummary[];
  detail: EvaluationBenchmarkDetailResponse | null;
  comparison: EvaluationComparisonResponse | null;
  skillSummary: EvaluationSkillSummaryResponse | null;
};

const EVAL_MODES: EvalMode[] = [
  {
    id: "effect",
    title: "这个 skill 有没有帮助",
    description: "对比不用 skill 和使用 skill 的结果。",
    baselineVariant: "no_skill",
    targetVariant: "with_skill",
    icon: <TrendingUp size={16} />,
  },
  {
    id: "version",
    title: "两个版本哪个更好",
    description: "对比 skill_v1 和 skill_v2。",
    baselineVariant: "skill_v1",
    targetVariant: "skill_v2",
    icon: <GitCompare size={16} />,
  },
  {
    id: "misfire",
    title: "会不会误触发",
    description: "检查不相关 skill 是否带来负面影响。",
    baselineVariant: "no_skill",
    targetVariant: "irrelevant_skill",
    icon: <ShieldAlert size={16} />,
  },
];

const panelStyle = {
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: "8px",
  background: "rgba(255,255,255,0.025)",
} satisfies CSSProperties;

const buttonStyle = {
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: "8px",
  background: "rgba(255,255,255,0.04)",
  color: "#f4f7ff",
  cursor: "pointer",
} satisfies CSSProperties;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function normalizeTask(task: EvaluationTaskDefinition): EvaluationTaskSummary | null {
  const taskId = typeof task.task_id === "string" ? task.task_id : null;
  if (!taskId) return null;
  const verifier = task.verifier;
  return {
    task_id: taskId,
    group: typeof task.group === "string" ? task.group : "-",
    eval_type: typeof task.eval_type === "string" ? task.eval_type : "-",
    target_skills: stringList(task.target_skills),
    variants: stringList(task.variants),
    verifier_configured:
      typeof task.verifier_configured === "boolean"
        ? task.verifier_configured
        : isRecord(verifier) && Object.keys(verifier).length > 0,
  };
}

function formatPercent(value: number | null | undefined): string {
  if (value == null) return "-";
  return `${Math.round(value * 100)}%`;
}

function formatScore(value: number | null | undefined): string {
  if (value == null) return "-";
  return value.toFixed(3);
}

function formatSigned(value: number | null | undefined): string {
  if (value == null) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(3)}`;
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

function EmptyState({ icon, title, detail }: { icon: ReactNode; title: string; detail?: string }) {
  return (
    <div style={{ ...panelStyle, padding: "14px", color: "rgba(255,255,255,0.58)", lineHeight: 1.5 }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "rgba(255,255,255,0.78)", fontWeight: 800 }}>
        {icon}
        <span>{title}</span>
      </div>
      {detail ? <div style={{ marginTop: "6px", fontSize: "12px" }}>{detail}</div> : null}
    </div>
  );
}

function SectionTitle({ children }: { children: ReactNode }) {
  return <div style={{ fontSize: "12px", fontWeight: 900, color: "rgba(255,255,255,0.76)", marginBottom: "8px" }}>{children}</div>;
}

function Metric({ label, value, tone = "plain" }: { label: string; value: string | number; tone?: "good" | "bad" | "plain" }) {
  const color = tone === "good" ? "#58d39a" : tone === "bad" ? "#ff8a8a" : "#f4f7ff";
  return (
    <div style={{ ...panelStyle, padding: "12px", minWidth: 0 }}>
      <div style={{ fontSize: "11px", color: "rgba(255,255,255,0.48)", marginBottom: "6px" }}>{label}</div>
      <div style={{ color, fontSize: "20px", fontWeight: 900, lineHeight: 1 }}>{value}</div>
    </div>
  );
}

function ModeCard({ mode, active, onClick }: { mode: EvalMode; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        ...panelStyle,
        padding: "12px",
        textAlign: "left",
        cursor: "pointer",
        background: active ? "rgba(118,165,255,0.14)" : panelStyle.background,
        borderColor: active ? "rgba(118,165,255,0.36)" : panelStyle.border,
        color: "rgba(255,255,255,0.72)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "#f4f7ff", fontWeight: 900, fontSize: "12px" }}>
        {mode.icon}
        <span>{mode.title}</span>
      </div>
      <div style={{ marginTop: "7px", fontSize: "11px", lineHeight: 1.45 }}>{mode.description}</div>
    </button>
  );
}

function TaskPicker({
  tasks,
  selectedTaskId,
  onSelect,
}: {
  tasks: EvaluationTaskSummary[];
  selectedTaskId: string | null;
  onSelect: (taskId: string) => void;
}) {
  if (tasks.length === 0) {
    return <EmptyState icon={<FileJson size={16} />} title="还没有可评估的 task" detail="先上传一个 task JSON，然后就能直接运行评估。" />;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      {tasks.slice(0, 10).map((task) => {
        const active = task.task_id === selectedTaskId;
        return (
          <button
            key={task.task_id}
            onClick={() => onSelect(task.task_id)}
            style={{
              ...panelStyle,
              padding: "10px 12px",
              textAlign: "left",
              cursor: "pointer",
              background: active ? "rgba(89,219,179,0.12)" : panelStyle.background,
              borderColor: active ? "rgba(89,219,179,0.34)" : panelStyle.border,
              color: "rgba(255,255,255,0.72)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ color: "#f4f7ff", fontWeight: 800, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{task.task_id}</span>
              {task.verifier_configured ? (
                <span style={{ marginLeft: "auto", color: "#58d39a", fontSize: "11px" }}>有结果校验</span>
              ) : (
                <span style={{ marginLeft: "auto", color: "#ffbf7a", fontSize: "11px" }}>缺少结果校验</span>
              )}
            </div>
            <div style={{ marginTop: "6px", fontSize: "11px", color: "rgba(255,255,255,0.5)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {task.target_skills.join(", ") || "未声明 skill"}
            </div>
          </button>
        );
      })}
    </div>
  );
}

function ResultSummary({ comparison }: { comparison: EvaluationComparisonResponse | null }) {
  const summary = comparison?.summary;
  const uplift = summary?.avg_result_score_uplift ?? null;
  const tone = uplift == null ? "plain" : uplift >= 0 ? "good" : "bad";
  const verdict =
    uplift == null
      ? "还没有足够的可比结果"
      : uplift > 0
        ? "结果：skill 有帮助"
        : uplift < 0
          ? "结果：skill 可能拖后腿"
          : "结果：暂时看不出差异";
  return (
    <div style={{ ...panelStyle, padding: "14px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "#f4f7ff", fontWeight: 900 }}>
        {tone === "bad" ? <TrendingDown size={16} color="#ff8a8a" /> : <TrendingUp size={16} color="#58d39a" />}
        <span>{verdict}</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "8px", marginTop: "12px" }}>
        <Metric label="result uplift" value={formatSigned(uplift)} tone={tone} />
        <Metric label="normalized gain" value={formatSigned(summary?.avg_normalized_gain)} tone={tone} />
        <Metric label="positive tasks" value={summary?.positive_tasks ?? 0} tone="good" />
        <Metric label="negative tasks" value={summary?.negative_tasks ?? 0} tone={(summary?.negative_tasks ?? 0) > 0 ? "bad" : "plain"} />
      </div>
    </div>
  );
}

function FailedCases({
  cases,
  onSelectRun,
}: {
  cases: EvaluationBenchmarkFailedCase[];
  onSelectRun?: (runId: string, sessionId?: string) => void;
}) {
  if (cases.length === 0) {
    return <EmptyState icon={<CheckCircle2 size={16} />} title="没有失败样本" detail="当前 benchmark 没有 result-first 失败 case。" />;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      {cases.map((item) => {
        const canOpen = Boolean(item.run_id && onSelectRun);
        return (
          <button
            key={`${item.session_id}:${item.run_id}:${item.task_id}:${item.variant_id}:${item.trial_index}`}
            onClick={canOpen ? () => onSelectRun?.(item.run_id as string, item.session_id) : undefined}
            style={{
              ...panelStyle,
              padding: "10px 12px",
              textAlign: "left",
              cursor: canOpen ? "pointer" : "default",
              color: "rgba(255,255,255,0.72)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <XCircle size={14} color="#ff8a8a" />
              <span style={{ color: "#f4f7ff", fontWeight: 800 }}>{item.task_id}</span>
              <span style={{ color: "rgba(255,255,255,0.45)", fontSize: "11px" }}>{item.variant_id}</span>
              {canOpen ? <MousePointer2 size={13} style={{ marginLeft: "auto", color: "rgba(255,255,255,0.42)" }} /> : null}
            </div>
            <div style={{ marginTop: "7px", color: "rgba(255,255,255,0.52)", fontSize: "11px" }}>
              result {formatScore(item.result_score)} | {item.failure_reason || item.error || item.notes[0] || "failed"}
            </div>
          </button>
        );
      })}
    </div>
  );
}

function MatrixTable({ rows }: { rows: EvaluationBenchmarkMatrixRow[] }) {
  if (rows.length === 0) {
    return <EmptyState icon={<BarChart3 size={16} />} title="没有 matrix 数据" />;
  }
  return (
    <div style={{ ...panelStyle, overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px", color: "rgba(255,255,255,0.72)" }}>
        <thead>
          <tr style={{ color: "rgba(255,255,255,0.46)" }}>
            <th style={thStyle}>task</th>
            <th style={thStyle}>variant</th>
            <th style={thStyle}>result</th>
            <th style={thStyle}>pass</th>
            <th style={thStyle}>weighted</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.task_id}:${row.variant_id}`} style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
              <td style={tdStyle}>{row.task_id}</td>
              <td style={tdStyle}>{row.variant_id}</td>
              <td style={tdStyle}>{formatScore(row.avg_result_score)}</td>
              <td style={tdStyle}>{formatPercent(row.result_pass_rate)}</td>
              <td style={tdStyle}>{formatScore(row.avg_weighted_score)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const thStyle: CSSProperties = {
  padding: "9px 8px",
  textAlign: "left",
  fontWeight: 800,
  whiteSpace: "nowrap",
};

const tdStyle: CSSProperties = {
  padding: "9px 8px",
  verticalAlign: "top",
  whiteSpace: "nowrap",
};

export function EvaluationPanel({
  sessionRuns,
  globalRuns,
  loading,
  activeRunId,
  onSelectRun,
}: EvaluationPanelProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [state, setState] = useState<LoadState>({
    overview: null,
    benchmarks: [],
    tasks: [],
    detail: null,
    comparison: null,
    skillSummary: null,
  });
  const [selectedModeId, setSelectedModeId] = useState<EvalModeId>("effect");
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [selectedBenchmarkId, setSelectedBenchmarkId] = useState<string | null>(null);
  const [importOverwrite, setImportOverwrite] = useState(false);
  const [isLoadingBase, setIsLoadingBase] = useState(true);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const selectedMode = EVAL_MODES.find((mode) => mode.id === selectedModeId) || EVAL_MODES[0];
  const selectedTask = state.tasks.find((task) => task.task_id === selectedTaskId) || null;
  const allRuns = useMemo(() => [...sessionRuns, ...globalRuns].slice(0, 6), [globalRuns, sessionRuns]);

  useEffect(() => {
    let cancelled = false;
    async function loadBase() {
      setIsLoadingBase(true);
      setError(null);
      try {
        const [overview, benchmarks, rawTasks] = await Promise.all([
          getEvaluationOverview(),
          listEvaluationBenchmarks(),
          listEvaluationTasks(),
        ]);
        if (cancelled) return;
        const tasks = rawTasks.map(normalizeTask).filter((task): task is EvaluationTaskSummary => task !== null);
        setState((prev) => ({ ...prev, overview, benchmarks, tasks }));
        setSelectedTaskId((current) => current || tasks[0]?.task_id || null);
        setSelectedBenchmarkId((current) => current || benchmarks[0]?.benchmark_id || null);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Evaluation 数据加载失败");
      } finally {
        if (!cancelled) setIsLoadingBase(false);
      }
    }
    void loadBase();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  useEffect(() => {
    let cancelled = false;
    async function loadDetail() {
      setIsLoadingDetail(true);
      try {
        const variants = {
          baselineVariant: selectedMode.baselineVariant,
          targetVariant: selectedMode.targetVariant,
        };
        const [detail, comparison] = selectedBenchmarkId
          ? await Promise.all([
              getEvaluationBenchmark(selectedBenchmarkId),
              getEvaluationComparisons(selectedBenchmarkId, variants),
            ])
          : await Promise.all([Promise.resolve(null), getEvaluationComparisons(undefined, variants)]);
        if (cancelled) return;
        const skill = selectedTask?.target_skills[0] || comparison.by_skill[0]?.skill || null;
        const skillSummary = skill ? await getEvaluationSkillSummary(skill) : null;
        if (cancelled) return;
        setState((prev) => ({ ...prev, detail, comparison, skillSummary }));
      } catch {
        if (!cancelled) setState((prev) => ({ ...prev, detail: null, comparison: null, skillSummary: null }));
      } finally {
        if (!cancelled) setIsLoadingDetail(false);
      }
    }
    void loadDetail();
    return () => {
      cancelled = true;
    };
  }, [selectedBenchmarkId, selectedMode.baselineVariant, selectedMode.targetVariant, selectedTask]);

  async function reloadAfterMutation(nextBenchmarkId?: string) {
    const [overview, benchmarks, rawTasks] = await Promise.all([
      getEvaluationOverview(),
      listEvaluationBenchmarks(),
      listEvaluationTasks(),
    ]);
    const tasks = rawTasks.map(normalizeTask).filter((task): task is EvaluationTaskSummary => task !== null);
    setState((prev) => ({ ...prev, overview, benchmarks, tasks }));
    if (nextBenchmarkId) setSelectedBenchmarkId(nextBenchmarkId);
    setSelectedTaskId((current) => current || tasks[0]?.task_id || null);
  }

  async function handleImportFile(file: File | null) {
    if (!file) return;
    setIsImporting(true);
    setMessage(null);
    setError(null);
    try {
      const text = await file.text();
      const parsed: unknown = JSON.parse(text);
      if (!isRecord(parsed)) throw new Error("task JSON 顶层必须是 object");
      const imported = await importEvaluationTask({ task: parsed, overwrite: importOverwrite });
      await reloadAfterMutation();
      setSelectedTaskId(imported.task_id);
      setMessage(`已导入 task：${imported.task_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "task 导入失败");
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
      setIsImporting(false);
    }
  }

  async function handleRun() {
    if (!selectedTaskId) {
      setError("请先选择或上传一个 task");
      return;
    }
    setIsRunning(true);
    setMessage("正在跑评估，完成后会自动打开结果。");
    setError(null);
    try {
      const result = await runEvaluationBenchmark({
        task_id: selectedTaskId,
        variants: [selectedMode.baselineVariant, selectedMode.targetVariant],
        trials: 1,
      });
      await reloadAfterMutation(result.benchmark_id);
      setMessage(`评估完成：${selectedTaskId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "评估执行失败");
    } finally {
      setIsRunning(false);
    }
  }

  const metrics = useMemo(() => {
    const summary = state.overview?.summary;
    const comp = state.comparison?.summary;
    const detail = state.detail;
    return [
      { label: "benchmarks", value: summary?.benchmark_count ?? 0, tone: "plain" as const },
      { label: "result pass", value: formatPercent(detail?.summary.pass_rate), tone: "plain" as const },
      {
        label: "result uplift",
        value: formatSigned(comp?.avg_result_score_uplift),
        tone: (comp?.avg_result_score_uplift ?? 0) >= 0 ? ("good" as const) : ("bad" as const),
      },
      {
        label: "failed cases",
        value: detail?.failed_cases.length ?? summary?.cases_failed ?? 0,
        tone: (detail?.failed_cases.length ?? summary?.cases_failed ?? 0) > 0 ? ("bad" as const) : ("plain" as const),
      },
    ];
  }, [state.comparison, state.detail, state.overview]);

  if (loading || isLoadingBase) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "24px", color: "rgba(255,255,255,0.55)" }}>
        <Loader2 size={16} style={{ animation: "spin 1s linear infinite" }} />
        正在加载 Skill Eval...
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px", padding: "12px 0", minWidth: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <BarChart3 size={17} color="rgba(255,255,255,0.72)" />
        <div style={{ color: "#f4f7ff", fontWeight: 900, fontSize: "13px" }}>Skill Eval Studio</div>
        <button
          onClick={() => setRefreshKey((value) => value + 1)}
          title="刷新 Skill Eval 数据"
          style={{ ...buttonStyle, marginLeft: "auto", width: "30px", height: "30px", display: "grid", placeItems: "center" }}
        >
          <RefreshCw size={14} />
        </button>
      </div>

      <div>
        <SectionTitle>你想评估什么？</SectionTitle>
        <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "8px" }}>
          {EVAL_MODES.map((mode) => (
            <ModeCard key={mode.id} mode={mode} active={mode.id === selectedModeId} onClick={() => setSelectedModeId(mode.id)} />
          ))}
        </div>
      </div>

      <div>
        <SectionTitle>选择 task</SectionTitle>
        <TaskPicker tasks={state.tasks} selectedTaskId={selectedTaskId} onSelect={setSelectedTaskId} />
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px", marginTop: "10px" }}>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json,.json"
            style={{ display: "none" }}
            onChange={(event) => void handleImportFile(event.target.files?.[0] || null)}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isImporting}
            style={{ ...buttonStyle, display: "inline-flex", alignItems: "center", gap: "7px", padding: "9px 11px", opacity: isImporting ? 0.6 : 1 }}
          >
            {isImporting ? <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> : <Upload size={14} />}
            上传 task JSON
          </button>
          <label style={{ display: "inline-flex", alignItems: "center", gap: "6px", color: "rgba(255,255,255,0.58)", fontSize: "11px" }}>
            <input type="checkbox" checked={importOverwrite} onChange={(event) => setImportOverwrite(event.target.checked)} />
            覆盖同名 task
          </label>
        </div>
      </div>

      <button
        onClick={() => void handleRun()}
        disabled={isRunning || !selectedTaskId}
        style={{
          ...buttonStyle,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: "8px",
          padding: "12px",
          background: selectedTaskId ? "rgba(89,219,179,0.14)" : "rgba(255,255,255,0.03)",
          borderColor: selectedTaskId ? "rgba(89,219,179,0.36)" : "rgba(255,255,255,0.08)",
          opacity: isRunning || !selectedTaskId ? 0.65 : 1,
        }}
      >
        {isRunning ? <Loader2 size={16} style={{ animation: "spin 1s linear infinite" }} /> : <Play size={16} />}
        {isRunning ? "正在跑评估" : "开始评估"}
      </button>

      {message ? <EmptyState icon={<CheckCircle2 size={16} />} title={message} /> : null}
      {error ? <EmptyState icon={<AlertTriangle size={16} />} title="操作失败" detail={error} /> : null}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "8px" }}>
        {metrics.map((metric) => (
          <Metric key={metric.label} label={metric.label} value={metric.value} tone={metric.tone} />
        ))}
      </div>

      {isLoadingDetail ? (
        <EmptyState icon={<Loader2 size={16} />} title="正在加载结果" />
      ) : (
        <>
          <ResultSummary comparison={state.comparison} />

          <div>
            <SectionTitle>失败样本</SectionTitle>
            <FailedCases cases={state.detail?.failed_cases || []} onSelectRun={onSelectRun} />
          </div>

          {state.comparison?.by_task.length ? (
            <div style={{ ...panelStyle, padding: "12px" }}>
              <SectionTitle>Task 变化</SectionTitle>
              <div style={{ display: "flex", flexDirection: "column", gap: "7px" }}>
                {state.comparison.by_task.slice(0, 6).map((task) => (
                  <div key={`${task.task_id}:${task.baseline_variant}:${task.target_variant}`} style={{ display: "flex", gap: "10px", color: "rgba(255,255,255,0.68)", fontSize: "11px" }}>
                    <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "#f4f7ff", fontWeight: 800 }}>{task.task_id}</span>
                    <span style={{ color: (task.result_score_uplift ?? 0) < 0 ? "#ff8a8a" : "#58d39a", fontWeight: 900 }}>{formatSigned(task.result_score_uplift)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </>
      )}

      <details style={{ ...panelStyle, padding: "12px", color: "rgba(255,255,255,0.62)" }}>
        <summary style={{ cursor: "pointer", color: "rgba(255,255,255,0.78)", fontWeight: 900, fontSize: "12px" }}>
          <SlidersHorizontal size={14} style={{ verticalAlign: "middle", marginRight: "6px" }} />
          高级详情
        </summary>
        <div style={{ marginTop: "10px", display: "flex", flexDirection: "column", gap: "10px" }}>
          <div style={{ fontSize: "11px", lineHeight: 1.6 }}>
            <div>benchmark: {selectedBenchmarkId || "-"}</div>
            <div>
              variants: {selectedMode.baselineVariant} vs {selectedMode.targetVariant}
            </div>
            <div>group: {selectedTask?.group || "-"}</div>
            <div>skill: {selectedTask?.target_skills.join(", ") || state.skillSummary?.summary.skill || "-"}</div>
          </div>
          <MatrixTable rows={state.detail?.matrix || []} />
          {state.benchmarks.length ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {state.benchmarks.slice(0, 5).map((benchmark) => (
                <button
                  key={benchmark.benchmark_id}
                  onClick={() => setSelectedBenchmarkId(benchmark.benchmark_id)}
                  style={{
                    ...panelStyle,
                    padding: "8px 10px",
                    textAlign: "left",
                    cursor: "pointer",
                    color: "rgba(255,255,255,0.64)",
                    background: benchmark.benchmark_id === selectedBenchmarkId ? "rgba(118,165,255,0.12)" : panelStyle.background,
                  }}
                >
                  <span style={{ color: "#f4f7ff", fontWeight: 800 }}>{benchmark.benchmark_id}</span>
                  <span style={{ marginLeft: "8px", fontSize: "11px", color: "rgba(255,255,255,0.45)" }}>{formatTime(benchmark.started_at)}</span>
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </details>

      {allRuns.length ? (
        <details style={{ ...panelStyle, padding: "12px", color: "rgba(255,255,255,0.62)" }}>
          <summary style={{ cursor: "pointer", color: "rgba(255,255,255,0.78)", fontWeight: 900, fontSize: "12px" }}>Debug Lab runs</summary>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginTop: "10px" }}>
            {allRuns.map((run) => {
              const active = run.run_id === activeRunId;
              return (
                <button
                  key={`${run.session_id}:${run.run_id}`}
                  onClick={onSelectRun ? () => onSelectRun(run.run_id, run.session_id) : undefined}
                  style={{
                    ...panelStyle,
                    padding: "8px 10px",
                    textAlign: "left",
                    cursor: onSelectRun ? "pointer" : "default",
                    color: "rgba(255,255,255,0.64)",
                    background: active ? "rgba(118,165,255,0.12)" : panelStyle.background,
                  }}
                >
                  <span style={{ color: "#f4f7ff", fontWeight: 800 }}>{run.task_id || "adhoc"}</span>
                  <span style={{ marginLeft: "8px", fontSize: "11px", color: "rgba(255,255,255,0.45)" }}>{run.status}</span>
                </button>
              );
            })}
          </div>
        </details>
      ) : null}
    </div>
  );
}

export default EvaluationPanel;
