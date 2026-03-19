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

export type WorkspaceTabKey = "artifacts" | "filesystem" | "skills" | "debug";
export type CenterMode = "chat" | "file";

