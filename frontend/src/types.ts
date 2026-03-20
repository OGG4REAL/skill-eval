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

