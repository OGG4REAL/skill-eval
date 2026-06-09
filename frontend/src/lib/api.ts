import type {
  ArtifactsRecord,
  EvalRecord,
  EvaluationBenchmarkDetailResponse,
  EvaluationBenchmarkListItem,
  EvaluationBenchmarkRunRequest,
  EvaluationBenchmarkRunResponse,
  EvaluationComparisonResponse,
  EvaluationOverviewResponse,
  EvaluationSkillSummaryResponse,
  EvaluationTaskDefinition,
  EvaluationTaskImportRequest,
  EvaluationTaskSummary,
  FileInfo,
  MessageResponse,
  RunIndexEntry,
  RunRecord,
  SessionSummary,
  TrajectoryEvent,
  WorkspaceFileResponse,
  WorkspaceTreeResponse,
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8001";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(msg || `Request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function createSession(): Promise<string> {
  const res = await fetch(`${API_BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  const data = await res.json();
  return data.session_id;
}

export async function listSessions(): Promise<SessionSummary[]> {
  return handleResponse<SessionSummary[]>(await fetch(`${API_BASE}/sessions`));
}

export async function uploadFiles(sessionId: string, files: File[]): Promise<void> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/files`, {
    method: "POST",
    body: form,
  });
  await handleResponse(res);
}

export async function listUploads(sessionId: string): Promise<FileInfo[]> {
  return handleResponse<FileInfo[]>(await fetch(`${API_BASE}/sessions/${sessionId}/files`));
}

export async function listOutputs(sessionId: string): Promise<FileInfo[]> {
  return handleResponse<FileInfo[]>(await fetch(`${API_BASE}/sessions/${sessionId}/outputs`));
}

export async function getWorkspace(sessionId: string): Promise<WorkspaceTreeResponse> {
  return handleResponse<WorkspaceTreeResponse>(
    await fetch(`${API_BASE}/sessions/${sessionId}/workspace`)
  );
}

export async function getWorkspaceFile(
  sessionId: string,
  path: string
): Promise<WorkspaceFileResponse> {
  const params = new URLSearchParams({ path });
  return handleResponse<WorkspaceFileResponse>(
    await fetch(`${API_BASE}/sessions/${sessionId}/workspace/file?${params.toString()}`)
  );
}

export function buildOutputUrl(sessionId: string, filename: string) {
  return `${API_BASE}/sessions/${sessionId}/outputs/${encodeURIComponent(filename)}`;
}

export async function sendMessage(
  sessionId: string,
  query: string,
  maxIterations?: number
): Promise<MessageResponse> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, max_iterations: maxIterations }),
  });
  return handleResponse<MessageResponse>(res);
}

export function openLogStream(sessionId: string, onLine: (line: string) => void): EventSource {
  const es = new EventSource(`${API_BASE}/sessions/${sessionId}/stream`);
  es.onmessage = (event) => {
    onLine(event.data);
  };
  es.onerror = () => {
    es.close();
  };
  return es;
}

// ============================================================================
// Run / Trajectory / Eval API
// ============================================================================

export async function listSessionRuns(sessionId: string): Promise<RunRecord[]> {
  return handleResponse<RunRecord[]>(
    await fetch(`${API_BASE}/sessions/${sessionId}/runs`)
  );
}

export async function getSessionRun(sessionId: string, runId: string): Promise<RunRecord> {
  return handleResponse<RunRecord>(
    await fetch(`${API_BASE}/sessions/${sessionId}/runs/${runId}`)
  );
}

export async function getRunTrajectory(sessionId: string, runId: string): Promise<TrajectoryEvent[]> {
  return handleResponse<TrajectoryEvent[]>(
    await fetch(`${API_BASE}/sessions/${sessionId}/runs/${runId}/trajectory`)
  );
}

export async function getRunArtifacts(sessionId: string, runId: string): Promise<ArtifactsRecord> {
  return handleResponse<ArtifactsRecord>(
    await fetch(`${API_BASE}/sessions/${sessionId}/runs/${runId}/artifacts`)
  );
}

export async function getRunEval(sessionId: string, runId: string): Promise<EvalRecord> {
  return handleResponse<EvalRecord>(
    await fetch(`${API_BASE}/sessions/${sessionId}/runs/${runId}/eval`)
  );
}

export async function listEvaluationRuns(limit: number = 50): Promise<RunIndexEntry[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  return handleResponse<RunIndexEntry[]>(
    await fetch(`${API_BASE}/evaluation/runs?${params.toString()}`)
  );
}

export async function listEvaluationTasks(): Promise<EvaluationTaskDefinition[]> {
  return handleResponse<EvaluationTaskDefinition[]>(
    await fetch(`${API_BASE}/evaluation/tasks`)
  );
}

export async function importEvaluationTask(
  request: EvaluationTaskImportRequest
): Promise<EvaluationTaskSummary> {
  const res = await fetch(`${API_BASE}/evaluation/tasks/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return handleResponse<EvaluationTaskSummary>(res);
}

export async function getEvaluationOverview(): Promise<EvaluationOverviewResponse> {
  return handleResponse<EvaluationOverviewResponse>(
    await fetch(`${API_BASE}/evaluation/overview`)
  );
}

export async function listEvaluationBenchmarks(): Promise<EvaluationBenchmarkListItem[]> {
  return handleResponse<EvaluationBenchmarkListItem[]>(
    await fetch(`${API_BASE}/evaluation/benchmarks`)
  );
}

export async function getEvaluationBenchmark(
  benchmarkId: string
): Promise<EvaluationBenchmarkDetailResponse> {
  return handleResponse<EvaluationBenchmarkDetailResponse>(
    await fetch(`${API_BASE}/evaluation/benchmarks/${encodeURIComponent(benchmarkId)}`)
  );
}

export async function getEvaluationSkillSummary(
  skill: string
): Promise<EvaluationSkillSummaryResponse> {
  return handleResponse<EvaluationSkillSummaryResponse>(
    await fetch(`${API_BASE}/evaluation/skills/${encodeURIComponent(skill)}/summary`)
  );
}

export async function getEvaluationComparisons(
  benchmarkId?: string,
  variants?: { baselineVariant?: string; targetVariant?: string }
): Promise<EvaluationComparisonResponse> {
  const params = new URLSearchParams();
  if (benchmarkId) params.set("benchmark_id", benchmarkId);
  if (variants?.baselineVariant) params.set("baseline_variant", variants.baselineVariant);
  if (variants?.targetVariant) params.set("target_variant", variants.targetVariant);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return handleResponse<EvaluationComparisonResponse>(
    await fetch(`${API_BASE}/evaluation/comparisons${suffix}`)
  );
}

export async function runEvaluationBenchmark(
  request: EvaluationBenchmarkRunRequest
): Promise<EvaluationBenchmarkRunResponse> {
  const res = await fetch(`${API_BASE}/evaluation/benchmarks/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return handleResponse<EvaluationBenchmarkRunResponse>(res);
}

