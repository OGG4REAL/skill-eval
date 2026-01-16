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

