import { ChevronDown, ChevronRight, Eye, FileText, FolderClosed, FolderOpen, PanelRightClose, RefreshCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { WorkspaceFileResponse, WorkspaceNode, WorkspaceTabKey } from "../../types";

interface WorkspacePanelProps {
  roots: WorkspaceNode[];
  loading?: boolean;
  error?: string | null;
  activeTab: WorkspaceTabKey;
  selectedPath?: string | null;
  previewFile?: WorkspaceFileResponse | null;
  previewLoading?: boolean;
  previewError?: string | null;
  onTabChange: (tab: WorkspaceTabKey) => void;
  onSelectFile: (path: string) => void;
  onOpenViewer: () => void;
  onToggleOpen: () => void;
  onRefresh: () => void;
}

const TAB_OPTIONS: Array<{ key: WorkspaceTabKey; label: string }> = [
  { key: "artifacts", label: "工件" },
  { key: "filesystem", label: "文件系统" },
  { key: "skills", label: "Skill" },
  { key: "debug", label: "调试" },
];

function formatFileSize(size?: number | null) {
  if (size === undefined || size === null) {
    return "未知大小";
  }
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function formatDateTime(value?: string | null) {
  if (!value) {
    return "未生成";
  }
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function collectDirectoryPaths(nodes: WorkspaceNode[]): string[] {
  const paths: string[] = [];
  for (const node of nodes) {
    if (node.kind === "directory") {
      paths.push(node.path);
      if (node.children?.length) {
        paths.push(...collectDirectoryPaths(node.children));
      }
    }
  }
  return paths;
}

function filterRootsByTab(roots: WorkspaceNode[], tab: WorkspaceTabKey) {
  switch (tab) {
    case "artifacts":
      return roots.filter((node) => node.path === "/workspace/output");
    case "skills":
      return roots.filter((node) => node.path === "/workspace/skills");
    case "debug":
      return roots.filter((node) =>
        [
          "/workspace/temp",
          "/workspace/.tool-results",
          "/workspace/chat.log",
          "/workspace/history.json",
        ].includes(node.path)
      );
    case "filesystem":
    default:
      return roots;
  }
}

interface TreeNodeProps {
  node: WorkspaceNode;
  depth?: number;
  expandedPaths: Set<string>;
  selectedPath?: string | null;
  onToggle: (path: string) => void;
  onSelectFile: (path: string) => void;
}

function TreeNode({
  node,
  depth = 0,
  expandedPaths,
  selectedPath,
  onToggle,
  onSelectFile,
}: TreeNodeProps) {
  const isDirectory = node.kind === "directory";
  const isExpanded = isDirectory && expandedPaths.has(node.path);
  const isSelected = node.kind === "file" && selectedPath === node.path;
  const iconColor = node.readonly ? "#f7d57e" : "rgba(255, 255, 255, 0.78)";

  return (
    <div>
      <button
        onClick={() => (isDirectory ? onToggle(node.path) : onSelectFile(node.path))}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: "8px",
          padding: "8px 10px",
          paddingLeft: `${10 + depth * 14}px`,
          borderRadius: "12px",
          border: "none",
          background: isSelected ? "rgba(118, 165, 255, 0.16)" : "transparent",
          color: isSelected ? "#ffffff" : "rgba(255, 255, 255, 0.76)",
          cursor: "pointer",
          textAlign: "left",
        }}
      >
        <span style={{ width: "14px", flexShrink: 0, color: "rgba(255, 255, 255, 0.48)" }}>
          {isDirectory ? (isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />) : null}
        </span>
        <span style={{ flexShrink: 0, color: iconColor }}>
          {isDirectory ? (isExpanded ? <FolderOpen size={15} /> : <FolderClosed size={15} />) : <FileText size={15} />}
        </span>
        <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {node.name}
        </span>
        {node.readonly ? (
          <span
            style={{
              marginLeft: "auto",
              padding: "2px 8px",
              borderRadius: "999px",
              border: "1px solid rgba(247, 213, 126, 0.22)",
              color: "#f7d57e",
              fontSize: "11px",
            }}
          >
            只读
          </span>
        ) : null}
      </button>

      {isDirectory && isExpanded && node.children?.length
        ? node.children.map((child) => (
            <TreeNode
              key={child.path}
              node={child}
              depth={depth + 1}
              expandedPaths={expandedPaths}
              selectedPath={selectedPath}
              onToggle={onToggle}
              onSelectFile={onSelectFile}
            />
          ))
        : null}

      {isDirectory && isExpanded && !node.children?.length ? (
        <div
          style={{
            paddingLeft: `${32 + depth * 14}px`,
            color: "rgba(255, 255, 255, 0.4)",
            fontSize: "12px",
            paddingTop: "4px",
            paddingBottom: "8px",
          }}
        >
          空目录
        </div>
      ) : null}
    </div>
  );
}

export function WorkspacePanel({
  roots,
  loading = false,
  error,
  activeTab,
  selectedPath,
  previewFile,
  previewLoading = false,
  previewError,
  onTabChange,
  onSelectFile,
  onOpenViewer,
  onToggleOpen,
  onRefresh,
}: WorkspacePanelProps) {
  const filteredRoots = useMemo(() => filterRootsByTab(roots, activeTab), [roots, activeTab]);
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());

  useEffect(() => {
    const next = new Set(expandedPaths);
    for (const path of collectDirectoryPaths(filteredRoots).slice(0, 8)) {
      next.add(path);
    }
    setExpandedPaths(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, roots]);

  const togglePath = (path: string) => {
    setExpandedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  return (
    <aside
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        borderRadius: "28px",
        background: "linear-gradient(180deg, rgba(9, 11, 20, 0.9), rgba(10, 14, 24, 0.82))",
        border: "1px solid rgba(255, 255, 255, 0.08)",
        boxShadow: "0 24px 60px rgba(0, 0, 0, 0.32)",
        overflow: "hidden",
      }}
    >
      <header
        style={{
          padding: "18px 18px 14px",
          borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "12px",
            marginBottom: "12px",
          }}
        >
          <div>
            <div style={{ fontSize: "16px", fontWeight: 700, color: "#f4f7ff" }}>Studio Workspace</div>
            <div style={{ marginTop: "4px", fontSize: "12px", color: "rgba(255, 255, 255, 0.52)" }}>
              当前会话的逻辑 /workspace 视图
            </div>
          </div>
          <div style={{ display: "flex", gap: "8px" }}>
            <button
              onClick={onRefresh}
              title="刷新 Workspace"
              style={{
                width: "34px",
                height: "34px",
                display: "grid",
                placeItems: "center",
                borderRadius: "12px",
                border: "1px solid rgba(255, 255, 255, 0.12)",
                background: "rgba(255, 255, 255, 0.04)",
                color: "rgba(255, 255, 255, 0.78)",
                cursor: "pointer",
              }}
            >
              <RefreshCcw size={15} />
            </button>
            <button
              onClick={onToggleOpen}
              title="收起侧栏"
              style={{
                width: "34px",
                height: "34px",
                display: "grid",
                placeItems: "center",
                borderRadius: "12px",
                border: "1px solid rgba(255, 255, 255, 0.12)",
                background: "rgba(255, 255, 255, 0.04)",
                color: "rgba(255, 255, 255, 0.78)",
                cursor: "pointer",
              }}
            >
              <PanelRightClose size={15} />
            </button>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px" }}>
          {TAB_OPTIONS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => onTabChange(tab.key)}
              style={{
                padding: "10px 8px",
                borderRadius: "12px",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                background:
                  activeTab === tab.key
                    ? "linear-gradient(135deg, rgba(118, 165, 255, 0.22), rgba(89, 219, 179, 0.16))"
                    : "rgba(255, 255, 255, 0.03)",
                color: activeTab === tab.key ? "#f4f7ff" : "rgba(255, 255, 255, 0.7)",
                cursor: "pointer",
                fontSize: "12px",
                fontWeight: 600,
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </header>

      <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
        <div
          style={{
            flex: 1,
            minHeight: 0,
            overflowY: "auto",
            padding: "16px 12px 12px",
          }}
        >
          {loading ? <div style={{ color: "rgba(255,255,255,0.55)" }}>正在加载 Workspace...</div> : null}
          {error ? (
            <div
              style={{
                padding: "14px",
                borderRadius: "14px",
                background: "rgba(255, 125, 125, 0.08)",
                border: "1px solid rgba(255, 125, 125, 0.15)",
                color: "rgba(255, 222, 222, 0.9)",
              }}
            >
              {error}
            </div>
          ) : null}
          {!loading && !error && filteredRoots.length === 0 ? (
            <div style={{ color: "rgba(255,255,255,0.45)" }}>当前标签下暂无可展示内容。</div>
          ) : null}
          {!loading && !error
            ? filteredRoots.map((node) => (
                <TreeNode
                  key={node.path}
                  node={node}
                  expandedPaths={expandedPaths}
                  selectedPath={selectedPath}
                  onToggle={togglePath}
                  onSelectFile={onSelectFile}
                />
              ))
            : null}
        </div>

        <div
          style={{
            borderTop: "1px solid rgba(255, 255, 255, 0.08)",
            padding: "14px 14px 16px",
            background: "rgba(255, 255, 255, 0.02)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "12px",
              marginBottom: "10px",
            }}
          >
            <div>
              <div style={{ color: "#f4f7ff", fontSize: "13px", fontWeight: 600 }}>即时预览</div>
              <div style={{ marginTop: "4px", color: "rgba(255,255,255,0.48)", fontSize: "11px" }}>
                默认展示全文，可切到中间区聚焦查看
              </div>
            </div>
            <button
              onClick={onOpenViewer}
              disabled={!previewFile}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 10px",
                borderRadius: "999px",
                border: "1px solid rgba(255, 255, 255, 0.12)",
                background: previewFile ? "rgba(118, 165, 255, 0.14)" : "rgba(255, 255, 255, 0.04)",
                color: previewFile ? "#f4f7ff" : "rgba(255, 255, 255, 0.32)",
                cursor: previewFile ? "pointer" : "not-allowed",
              }}
            >
              <Eye size={14} />
              展开查看
            </button>
          </div>

          <div
            style={{
              minHeight: "210px",
              maxHeight: "260px",
              overflowY: "auto",
              borderRadius: "18px",
              border: "1px solid rgba(255, 255, 255, 0.08)",
              background: "rgba(0, 0, 0, 0.22)",
              padding: "14px",
            }}
          >
            {previewLoading ? <div style={{ color: "rgba(255,255,255,0.55)" }}>正在读取文件...</div> : null}
            {previewError ? (
              <div style={{ color: "rgba(255, 209, 209, 0.92)", lineHeight: 1.6 }}>{previewError}</div>
            ) : null}
            {!previewLoading && !previewError && !previewFile ? (
              <div style={{ color: "rgba(255,255,255,0.45)", lineHeight: 1.6 }}>
                从上方文件树选择一个文件后，这里会展示即时预览。
              </div>
            ) : null}
            {!previewError && previewFile ? (
              <>
                <div style={{ marginBottom: "12px" }}>
                  <div
                    style={{
                      color: "#f3f7ff",
                      fontSize: "13px",
                      fontWeight: 600,
                      wordBreak: "break-all",
                    }}
                  >
                    {previewFile.path}
                  </div>
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "8px",
                      marginTop: "6px",
                      fontSize: "11px",
                      color: "rgba(255,255,255,0.48)",
                    }}
                  >
                    <span>{formatFileSize(previewFile.size)}</span>
                    <span>{formatDateTime(previewFile.modified)}</span>
                    {previewFile.readonly ? <span>只读</span> : null}
                  </div>
                </div>
                <pre
                  style={{
                    margin: 0,
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                    fontSize: "12px",
                    lineHeight: 1.6,
                    color: "rgba(255,255,255,0.86)",
                    fontFamily: '"SF Mono", "SFMono-Regular", ui-monospace, monospace',
                  }}
                >
                  {previewFile.content}
                </pre>
              </>
            ) : null}
          </div>
        </div>
      </div>
    </aside>
  );
}

export default WorkspacePanel;
