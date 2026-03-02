import type { FileInfo, MessageResponse, SessionSummary } from "../types";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

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

