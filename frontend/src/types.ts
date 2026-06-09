export interface SessionSummary {
  session_id: string;
  base: string;
  uploads: string;
  output: string;
}

export interface FileInfo {
  name: string;
  size: number;
  modified: string;
}

export interface MessageResponse {
  stdout: string;
  stderr: string;
  returncode: number;
  log: string;
}

export type WorkspaceNodeKind = "file" | "directory";

export interface WorkspaceNode {
  path: string;
  name: string;
  kind: WorkspaceNodeKind;
  size?: number | null;
  modified?: string | null;
  readonly: boolean;
  children?: WorkspaceNode[] | null;
}

export interface WorkspaceTreeResponse {
  session_id: string;
  roots: WorkspaceNode[];
}

export interface WorkspaceFileResponse {
  path: string;
  name: string;
  size: number;
  modified: string;
  readonly: boolean;
  content: string;
  language?: string | null;
  mime_type: string;
  truncated: boolean;
}

export type WorkspaceTabKey = "filesystem" | "skills" | "trajectory" | "evaluation";
export type CenterMode = "chat" | "file";

// ============================================================================
// Run / Trajectory / Eval 类型
// ============================================================================

export interface RunRecord {
  run_id: string;
  session_id: string;
  task_id: string;
  variant_id: string;
  skills: string[];
  trigger: string;
  user_input: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  status: "running" | "passed" | "failed";
  iterations: number;
  tool_calls: number;
  tool_errors: number;
}

export interface TrajectoryEvent {
  type: string;
  run_id: string;
  timestamp: string;
  step_index?: number;
  iteration?: number;
  tool_name?: string;
  arguments?: Record<string, unknown>;
  status?: string;
  duration_ms?: number;
  message?: string;
  model?: string;
  provider?: string;
  usage?: Record<string, unknown>;
  path?: string;
  skills?: string[];
  error?: string;
}

export interface EvalScores {
  task_success: number | null;
  tool_efficiency: number | null;
  artifact_completeness: number | null;
  trajectory_quality: number | null;
}

export interface EvalRecord {
  run_id: string;
  task_id: string;
  variant_id: string;
  status: string;
  metrics: Record<string, number | null>;
  scores: EvalScores;
  notes: string[];
}

export interface ArtifactsRecord {
  run_id: string;
  files: string[];
}

export interface RunIndexEntry {
  run_id: string;
  session_id: string;
  task_id: string;
  variant_id: string;
  skills: string[];
  status: string;
  score: number | null;
  duration_ms: number | null;
  tool_calls: number;
  created_at: string;
}

// ============================================================================
// Evaluation API Contract 类型
// ============================================================================

export interface EvaluationScope {
  task_id: string | null;
  group: string | null;
  all: boolean;
  variants: string[];
  trials: number;
}

export interface EvaluationBenchmarkSummary {
  cases_total: number;
  cases_succeeded: number;
  cases_failed: number;
  pass_rate: number | null;
  task_count: number;
  variant_count: number;
}

export interface EvaluationComparisonSummary {
  source: string;
  generated_at: string | null;
  baseline_variant: string;
  target_variant: string;
  tasks_compared: number;
  skills_compared: number;
  positive_tasks: number;
  negative_tasks: number;
  neutral_tasks: number;
  avg_result_score_uplift: number | null;
  avg_normalized_gain: number | null;
}

export interface EvaluationBenchmarkListItem {
  benchmark_id: string;
  started_at: string | null;
  finished_at: string | null;
  scope: EvaluationScope;
  summary: EvaluationBenchmarkSummary;
  comparison_summary?: EvaluationComparisonSummary;
}

export interface EvaluationOverviewResponse {
  summary: {
    benchmark_count: number;
    task_count: number;
    skill_count: number;
    latest_benchmark_id: string | null;
    latest_started_at: string | null;
    cases_total: number;
    cases_failed: number;
    positive_comparisons: number;
    negative_comparisons: number;
  };
  latest_benchmarks: EvaluationBenchmarkListItem[];
  comparison_summary: EvaluationComparisonSummary;
  warnings: string[];
}

export interface EvaluationBenchmarkMatrixRow {
  task_id: string;
  variant_id: string;
  trials: number;
  pass_rate: number | null;
  result_pass_rate: number | null;
  avg_result_score: number | null;
  avg_weighted_score: number | null;
  avg_duration_ms: number | null;
  avg_tool_calls: number | null;
  avg_tool_errors: number | null;
}

export interface EvaluationBenchmarkRunRef {
  task_id: string;
  variant_id: string;
  trial_index: number;
  session_id: string;
  run_id: string | null;
  status: string;
  run_status: string | null;
  result_pass: boolean | null;
  result_score: number | null;
}

export interface EvaluationBenchmarkFailedCase extends EvaluationBenchmarkRunRef {
  error: string | null;
  failure_reason: string | null;
  notes: string[];
}

export interface EvaluationTaskDelta {
  task_id: string;
  skill: string | null;
  baseline_variant: string;
  target_variant: string;
  baseline_result_score: number | null;
  target_result_score: number | null;
  result_score_uplift: number | null;
  normalized_gain: number | null;
  baseline_result_pass_rate: number | null;
  target_result_pass_rate: number | null;
  result_pass_rate_uplift: number | null;
  baseline_score: number | null;
  target_score: number | null;
  score_uplift: number | null;
  baseline_pass_rate: number | null;
  target_pass_rate: number | null;
  pass_rate_uplift: number | null;
  baseline_avg_duration_ms: number | null;
  target_avg_duration_ms: number | null;
  duration_diff_ms: number | null;
  verdict: string;
}

export interface EvaluationSkillDelta {
  skill: string;
  tasks: number;
  baseline_result_avg: number | null;
  target_result_avg: number | null;
  avg_result_score_uplift: number | null;
  avg_normalized_gain: number | null;
  baseline_avg: number | null;
  skill_avg: number | null;
  avg_uplift: number | null;
  positive_tasks: string[];
  negative_tasks: string[];
  neutral_tasks: string[];
}

export interface EvaluationComparisonResponse {
  summary: EvaluationComparisonSummary;
  by_skill: EvaluationSkillDelta[];
  by_task: EvaluationTaskDelta[];
  source: string;
  generated_at: string | null;
  warnings: string[];
}

export interface EvaluationBenchmarkDetailResponse extends EvaluationBenchmarkListItem {
  matrix: EvaluationBenchmarkMatrixRow[];
  failed_cases: EvaluationBenchmarkFailedCase[];
  run_refs: EvaluationBenchmarkRunRef[];
  comparison: EvaluationComparisonResponse | null;
}

export interface EvaluationSkillSummaryResponse {
  summary: {
    skill: string;
    tasks_compared: number;
    positive_tasks: number;
    negative_tasks: number;
    neutral_tasks: number;
    avg_result_score_uplift: number | null;
    avg_normalized_gain: number | null;
    baseline_result_avg: number | null;
    target_result_avg: number | null;
  };
  tasks: EvaluationTaskDelta[];
  recent_benchmarks: EvaluationBenchmarkListItem[];
  warnings: string[];
}

export interface EvaluationBenchmarkRunRequest {
  task_id?: string | null;
  group?: string | null;
  all?: boolean;
  variants?: string[] | null;
  trials?: number;
}

export interface EvaluationBenchmarkRunResponse {
  benchmark_id: string;
  summary: EvaluationBenchmarkSummary;
  benchmark: EvaluationBenchmarkListItem;
}

export interface EvaluationTaskSummary {
  task_id: string;
  group: string;
  eval_type: string;
  target_skills: string[];
  variants: string[];
  verifier_configured: boolean;
}

export interface EvaluationTaskImportRequest {
  task: Record<string, unknown>;
  overwrite?: boolean;
}

export type EvaluationTaskDefinition = Record<string, unknown>;

