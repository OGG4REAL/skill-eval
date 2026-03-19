import { ArrowLeft, FileText, RefreshCcw } from "lucide-react";

import type { WorkspaceFileResponse } from "../../types";
import { MarkdownRenderer } from "./MarkdownRenderer";

interface FileViewerProps {
  file: WorkspaceFileResponse | null;
  loading?: boolean;
  error?: string | null;
  onBack: () => void;
  onRefresh?: () => void;
}

function formatFileSize(size: number) {
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function renderContent(file: WorkspaceFileResponse) {
  if (file.language === "markdown") {
    return <MarkdownRenderer content={file.content} />;
  }

  return (
    <pre
      style={{
        margin: 0,
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        fontSize: "13px",
        lineHeight: 1.65,
        fontFamily: '"SF Mono", "SFMono-Regular", ui-monospace, monospace',
        color: "rgba(255, 255, 255, 0.88)",
      }}
    >
      {file.content}
    </pre>
  );
}

export function FileViewer({ file, loading = false, error, onBack, onRefresh }: FileViewerProps) {
  return (
    <section
      style={{
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        height: "100%",
        borderRadius: "26px",
        background: "rgba(8, 10, 20, 0.55)",
        border: "1px solid rgba(255, 255, 255, 0.08)",
        boxShadow: "0 24px 60px rgba(0, 0, 0, 0.32)",
        overflow: "hidden",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "16px",
          padding: "18px 22px",
          borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
          background: "linear-gradient(180deg, rgba(118, 165, 255, 0.08), rgba(118, 165, 255, 0.02))",
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              marginBottom: "6px",
            }}
          >
            <button
              onClick={onBack}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 12px",
                borderRadius: "999px",
                border: "1px solid rgba(255, 255, 255, 0.12)",
                background: "rgba(255, 255, 255, 0.04)",
                color: "rgba(255, 255, 255, 0.82)",
                cursor: "pointer",
              }}
            >
              <ArrowLeft size={14} />
                返回会话
            </button>
            {onRefresh && (
              <button
                onClick={onRefresh}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "8px 12px",
                  borderRadius: "999px",
                  border: "1px solid rgba(255, 255, 255, 0.12)",
                  background: "rgba(255, 255, 255, 0.04)",
                  color: "rgba(255, 255, 255, 0.75)",
                  cursor: "pointer",
                }}
              >
                <RefreshCcw size={14} />
                刷新
              </button>
            )}
          </div>
          <div
            style={{
              fontSize: "15px",
              fontWeight: 600,
              color: "#f3f7ff",
              wordBreak: "break-all",
            }}
          >
            {file?.path ?? "文件查看"}
          </div>
          <div
            style={{
              marginTop: "6px",
              display: "flex",
              flexWrap: "wrap",
              gap: "8px",
              fontSize: "12px",
              color: "rgba(255, 255, 255, 0.58)",
            }}
          >
            {file && <span>{formatFileSize(file.size)}</span>}
            {file && <span>{formatDateTime(file.modified)}</span>}
            {file && (
              <span
                style={{
                  padding: "2px 8px",
                  borderRadius: "999px",
                  border: "1px solid rgba(255, 255, 255, 0.12)",
                  color: file.readonly ? "#f7d57e" : "rgba(255, 255, 255, 0.7)",
                }}
              >
                {file.readonly ? "只读" : "可读"}
              </span>
            )}
          </div>
        </div>
        <div
          style={{
            width: "44px",
            height: "44px",
            borderRadius: "14px",
            display: "grid",
            placeItems: "center",
            background: "rgba(255, 255, 255, 0.05)",
            color: "rgba(255, 255, 255, 0.75)",
            flexShrink: 0,
          }}
        >
          <FileText size={18} />
        </div>
      </header>

      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: "auto",
          padding: "22px",
        }}
      >
        {loading && !file ? (
          <div style={{ color: "rgba(255, 255, 255, 0.58)" }}>正在读取文件...</div>
        ) : null}
        {error ? (
          <div
            style={{
              padding: "18px",
              borderRadius: "18px",
              background: "rgba(255, 125, 125, 0.08)",
              border: "1px solid rgba(255, 125, 125, 0.18)",
              color: "rgba(255, 219, 219, 0.92)",
            }}
          >
            {error}
          </div>
        ) : null}
        {!loading && !error && !file ? (
          <div style={{ color: "rgba(255, 255, 255, 0.52)" }}>从右侧 Studio Workspace 选择一个文件开始查看。</div>
        ) : null}
        {!error && file ? renderContent(file) : null}
      </div>
    </section>
  );
}

export default FileViewer;
