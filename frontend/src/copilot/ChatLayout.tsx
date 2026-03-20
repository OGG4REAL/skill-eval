/**
 * ChatLayout - 三栏工作台布局
 *
 * 保留现有流式聊天协议，在中间区增加文件查看模式，
 * 并在右侧接入逻辑 /workspace 的浏览、预览和放大查看。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Download, FileUp, Loader2, PanelRightOpen, Send, Trash2 } from "lucide-react";

import { ChartAction, NotificationAction, TableAction } from "./actions";
import { FileViewer, MarkdownRenderer, ThinkingPanel, WorkspacePanel, WorkspaceResizeHandle } from "./components";
import {
  getRunArtifacts,
  getRunEval,
  getRunTrajectory,
  getSessionRun,
  getWorkspace,
  getWorkspaceFile,
  listEvaluationRuns,
  listSessionRuns,
  listUploads,
  uploadFiles,
} from "../lib/api";
import { downloadReport } from "../lib/reportGenerator";
import type {
  ArtifactsRecord,
  CenterMode,
  EvalRecord,
  FileInfo,
  RunIndexEntry,
  RunRecord,
  TrajectoryEvent,
  WorkspaceFileResponse,
  WorkspaceNode,
  WorkspaceTabKey,
} from "../types";
import type {
  ChatMessage,
  RenderChartArgs,
  RenderTableArgs,
  ShowNotificationArgs,
  SSEToolCallEvent,
  ThinkingStep,
} from "./types";

const WORKSPACE_WIDTH_KEY = "copilot_workspace_width";
const WORKSPACE_OPEN_KEY = "copilot_workspace_open";
const DEFAULT_WORKSPACE_WIDTH = 400;
const MIN_WORKSPACE_WIDTH = 320;
const MAX_WORKSPACE_WIDTH = 720;
const TOP_SAFE_AREA = 72;

const generateId = () => `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;

function getInitialWorkspaceWidth() {
  const stored = window.localStorage.getItem(WORKSPACE_WIDTH_KEY);
  const parsed = stored ? Number.parseInt(stored, 10) : NaN;
  if (Number.isNaN(parsed)) {
    return DEFAULT_WORKSPACE_WIDTH;
  }
  return Math.min(Math.max(parsed, MIN_WORKSPACE_WIDTH), MAX_WORKSPACE_WIDTH);
}

function getInitialWorkspaceOpen() {
  return window.localStorage.getItem(WORKSPACE_OPEN_KEY) !== "false";
}

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "未知错误";
}

function parseToolArguments(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object") {
    return value as Record<string, unknown>;
  }
  if (typeof value !== "string") {
    return {};
  }
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function buildMessagesFromHistory(rawHistory: unknown): ChatMessage[] {
  if (!Array.isArray(rawHistory)) {
    return [];
  }

  const restored: ChatMessage[] = [];
  let pendingToolCalls: SSEToolCallEvent[] = [];

  for (const entry of rawHistory) {
    if (!entry || typeof entry !== "object") {
      continue;
    }

    const record = entry as Record<string, unknown>;
    const role = record.role;
    const content = typeof record.content === "string" ? record.content : "";
    const toolCallSource = Array.isArray(record.tool_calls) ? record.tool_calls : [];

    if (role === "user" && content.trim()) {
      restored.push({
        id: generateId(),
        role: "user",
        content,
        timestamp: Date.now() + restored.length,
      });
      continue;
    }

    if (role !== "assistant") {
      continue;
    }

    if (toolCallSource.length > 0) {
      pendingToolCalls = toolCallSource
        .map((item) => {
          if (!item || typeof item !== "object") {
            return null;
          }
          const functionData =
            "function" in item && item.function && typeof item.function === "object"
              ? (item.function as Record<string, unknown>)
              : null;
          if (!functionData || typeof functionData.name !== "string") {
            return null;
          }
          return {
            name: functionData.name,
            arguments: parseToolArguments(functionData.arguments),
          } satisfies SSEToolCallEvent;
        })
        .filter((toolCall): toolCall is SSEToolCallEvent => Boolean(toolCall));
    }

    if (!content.trim()) {
      continue;
    }

    restored.push({
      id: generateId(),
      role: "assistant",
      content,
      toolCalls: pendingToolCalls.length > 0 ? pendingToolCalls : undefined,
      timestamp: Date.now() + restored.length,
    });
    pendingToolCalls = [];
  }

  return restored;
}

interface ChatLayoutProps {
  sessionId?: string;
}

export function ChatLayout({ sessionId }: ChatLayoutProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [currentThinking, setCurrentThinking] = useState<ThinkingStep[]>([]);
  const [toolCalls, setToolCalls] = useState<SSEToolCallEvent[]>([]);
  const [uploads, setUploads] = useState<FileInfo[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  const [workspaceRoots, setWorkspaceRoots] = useState<WorkspaceNode[]>([]);
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [workspaceOpen, setWorkspaceOpen] = useState(getInitialWorkspaceOpen);
  const [workspaceWidth, setWorkspaceWidth] = useState(getInitialWorkspaceWidth);
  const [workspaceTab, setWorkspaceTab] = useState<WorkspaceTabKey>("filesystem");
  const [selectedWorkspacePath, setSelectedWorkspacePath] = useState<string | null>(null);
  const [selectedWorkspaceFile, setSelectedWorkspaceFile] = useState<WorkspaceFileResponse | null>(null);
  const [workspacePreviewLoading, setWorkspacePreviewLoading] = useState(false);
  const [workspacePreviewError, setWorkspacePreviewError] = useState<string | null>(null);
  const [centerMode, setCenterMode] = useState<CenterMode>("chat");

  // Run / Trajectory / Eval 状态
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [currentRun, setCurrentRun] = useState<RunRecord | null>(null);
  const [currentTrajectory, setCurrentTrajectory] = useState<TrajectoryEvent[]>([]);
  const [currentEval, setCurrentEval] = useState<EvalRecord | null>(null);
  const [currentArtifacts, setCurrentArtifacts] = useState<ArtifactsRecord | null>(null);
  const [sessionRuns, setSessionRuns] = useState<RunRecord[]>([]);
  const [globalRuns, setGlobalRuns] = useState<RunIndexEntry[]>([]);
  const [runLoading, setRunLoading] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const uploadInputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const refreshUploads = useCallback(async () => {
    if (!sessionId) {
      setUploads([]);
      return;
    }
    try {
      const nextUploads = await listUploads(sessionId);
      setUploads(nextUploads);
    } catch {
      setUploads([]);
    }
  }, [sessionId]);

  const refreshWorkspace = useCallback(async () => {
    if (!sessionId) {
      setWorkspaceRoots([]);
      return;
    }
    setWorkspaceLoading(true);
    setWorkspaceError(null);
    try {
      const data = await getWorkspace(sessionId);
      setWorkspaceRoots(data.roots);
    } catch (error) {
      setWorkspaceError(getErrorMessage(error));
      setWorkspaceRoots([]);
    } finally {
      setWorkspaceLoading(false);
    }
  }, [sessionId]);

  const loadWorkspaceFile = useCallback(
    async (path: string, options?: { openViewer?: boolean; targetSessionId?: string }) => {
      const effectiveSessionId = options?.targetSessionId || sessionId;
      if (!effectiveSessionId) {
        return;
      }
      setSelectedWorkspacePath(path);
      setWorkspacePreviewLoading(true);
      setWorkspacePreviewError(null);
      try {
        const file = await getWorkspaceFile(effectiveSessionId, path);
        setSelectedWorkspaceFile(file);
        if (options?.openViewer) {
          setCenterMode("file");
        }
      } catch (error) {
        setSelectedWorkspaceFile(null);
        setWorkspacePreviewError(getErrorMessage(error));
      } finally {
        setWorkspacePreviewLoading(false);
      }
    },
    [sessionId]
  );

  const refreshRunData = useCallback(async (runId?: string) => {
    if (!sessionId) return;
    setRunLoading(true);
    try {
      const [runs, global] = await Promise.all([
        listSessionRuns(sessionId),
        listEvaluationRuns(30),
      ]);
      setSessionRuns(runs);
      setGlobalRuns(global);

      let targetRunId = runId || (runs.length > 0 ? runs[0].run_id : null);
      let targetSessionId = sessionId;

      // 当前 session 无 run 时，自动选中全局最近的一条
      if (!targetRunId && global.length > 0) {
        targetRunId = global[0].run_id;
        targetSessionId = global[0].session_id;
      }

      if (targetRunId) {
        setActiveRunId(targetRunId);
        const [run, trajectory, evalResult, artifactsResult] = await Promise.all([
          getSessionRun(targetSessionId, targetRunId).catch(() => null),
          getRunTrajectory(targetSessionId, targetRunId).catch(() => []),
          getRunEval(targetSessionId, targetRunId).catch(() => null),
          getRunArtifacts(targetSessionId, targetRunId).catch(() => null),
        ]);
        setCurrentRun(run);
        setCurrentTrajectory(trajectory);
        setCurrentEval(evalResult);
        setCurrentArtifacts(artifactsResult);
      } else {
        setActiveRunId(null);
        setCurrentRun(null);
        setCurrentTrajectory([]);
        setCurrentEval(null);
        setCurrentArtifacts(null);
      }
    } catch (error) {
      console.error("加载 run 数据失败:", error);
    } finally {
      setRunLoading(false);
    }
  }, [sessionId]);

  const handleSelectRun = useCallback(async (runId: string, ownerSessionId?: string) => {
    const targetSession = ownerSessionId || sessionId;
    if (!targetSession) return;
    setActiveRunId(runId);
    setRunLoading(true);
    try {
      const [run, trajectory, evalResult, artifactsResult] = await Promise.all([
        getSessionRun(targetSession, runId).catch(() => null),
        getRunTrajectory(targetSession, runId).catch(() => []),
        getRunEval(targetSession, runId).catch(() => null),
        getRunArtifacts(targetSession, runId).catch(() => null),
      ]);
      setCurrentRun(run);
      setCurrentTrajectory(trajectory);
      setCurrentEval(evalResult);
      setCurrentArtifacts(artifactsResult);
    } catch (error) {
      console.error("加载 run 详情失败:", error);
    } finally {
      setRunLoading(false);
    }
  }, [sessionId]);

  const loadConversationHistory = useCallback(async () => {
    if (!sessionId) {
      setMessages([]);
      return;
    }

    try {
      const historyFile = await getWorkspaceFile(sessionId, "/workspace/history.json");
      const parsed = JSON.parse(historyFile.content) as unknown;
      setMessages(buildMessagesFromHistory(parsed));
    } catch (error) {
      console.error("加载历史消息失败:", error);
      setMessages([]);
    }
  }, [sessionId]);

  useEffect(() => {
    scrollToBottom();
  }, [messages, currentThinking, scrollToBottom]);

  useEffect(() => {
    void refreshUploads();
    void refreshWorkspace();
    void loadConversationHistory();
    void refreshRunData();
    setInputValue("");
    setIsLoading(false);
    setCurrentThinking([]);
    setToolCalls([]);
    setSelectedWorkspacePath(null);
    setSelectedWorkspaceFile(null);
    setWorkspacePreviewError(null);
    setCenterMode("chat");
    setActiveRunId(null);
    setCurrentRun(null);
    setCurrentTrajectory([]);
    setCurrentEval(null);
    setCurrentArtifacts(null);
    setSessionRuns([]);
  }, [loadConversationHistory, refreshUploads, refreshWorkspace, refreshRunData]);

  useEffect(() => {
    window.localStorage.setItem(WORKSPACE_WIDTH_KEY, String(workspaceWidth));
  }, [workspaceWidth]);

  useEffect(() => {
    window.localStorage.setItem(WORKSPACE_OPEN_KEY, String(workspaceOpen));
  }, [workspaceOpen]);

  const handleSendMessage = async (overrideInput?: string) => {
    const trimmedInput = (overrideInput ?? inputValue).trim();
    if (!trimmedInput || isLoading || !sessionId) return;

    const userMessage: ChatMessage = {
      id: generateId(),
      role: "user",
      content: trimmedInput,
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue("");
    setIsLoading(true);
    setCurrentThinking([]);
    setToolCalls([]);
    setCenterMode("chat");

    let doneRunId: string | null = null;

    try {
      const response = await fetch("/copilotkit/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          messages: [...messages, userMessage].map((message) => ({
            role: message.role,
            content: message.content,
          })),
          session_id: sessionId,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("No response body");
      }

      const decoder = new TextDecoder();
      let buffer = "";
      let assistantContent = "";
      let streamError = "";
      const thinkingSteps: ThinkingStep[] = [];
      const collectedToolCalls: SSEToolCallEvent[] = [];
      let collectedSuggestions: string[] = [];
      let currentEventType = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEventType = line.slice(7).trim();
            continue;
          }
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));

              if (currentEventType === "done") {
                if (data.run_id) {
                  doneRunId = data.run_id;
                }
              } else if (currentEventType === "error") {
                streamError = data.message || "未知错误";
              } else if (currentEventType === "suggestions") {
                if (Array.isArray(data.questions)) {
                  collectedSuggestions = data.questions;
                }
              } else if (data.type === "thinking") {
                const step: ThinkingStep = {
                  id: generateId(),
                  type: "thinking",
                  content: data.content,
                  timestamp: Date.now(),
                };
                thinkingSteps.push(step);
                setCurrentThinking([...thinkingSteps]);
              } else if (data.type === "tool_call") {
                const step: ThinkingStep = {
                  id: generateId(),
                  type: "tool_call",
                  content: data.content,
                  timestamp: Date.now(),
                };
                thinkingSteps.push(step);
                setCurrentThinking([...thinkingSteps]);
              } else if (data.type === "tool_result") {
                const step: ThinkingStep = {
                  id: generateId(),
                  type: "tool_result",
                  content: data.content,
                  timestamp: Date.now(),
                };
                thinkingSteps.push(step);
                setCurrentThinking([...thinkingSteps]);
              } else if (data.type === "response") {
                assistantContent = data.content;
              } else if (data.name) {
                collectedToolCalls.push({
                  name: data.name,
                  arguments: data.arguments,
                });
                setToolCalls([...collectedToolCalls]);
              }
            } catch {
              // 忽略非 JSON 数据
            }
            currentEventType = "";
          }
        }
      }

      if (streamError) {
        throw new Error(streamError);
      }

      const assistantMessage: ChatMessage = {
        id: generateId(),
        role: "assistant",
        content: assistantContent,
        thinking: thinkingSteps,
        toolCalls: collectedToolCalls,
        suggestedQuestions: collectedSuggestions.length > 0 ? collectedSuggestions : undefined,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, assistantMessage]);
      setCurrentThinking([]);
    } catch (error) {
      console.error("Failed to send message:", error);
      const errorMessage: ChatMessage = {
        id: generateId(),
        role: "assistant",
        content: `抱歉，发生了错误：${getErrorMessage(error)}`,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
      void refreshWorkspace();
      void refreshRunData(doneRunId ?? undefined);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSendMessage();
    }
  };

  const handleExportReport = () => {
    if (!sessionId || messages.length === 0) return;
    downloadReport(sessionId, messages);
  };

  const handleClearChat = () => {
    setMessages([]);
    setCurrentThinking([]);
    setToolCalls([]);
    setCenterMode("chat");
  };

  const handleUpload = async (files: FileList | null) => {
    if (!files || !sessionId) return;
    setIsUploading(true);
    try {
      await uploadFiles(sessionId, Array.from(files));
      await Promise.all([refreshUploads(), refreshWorkspace()]);
    } catch (error) {
      console.error("上传失败:", error);
    } finally {
      setIsUploading(false);
    }
  };

  const handleSuggestionClick = (question: string) => {
    if (isLoading || !sessionId) return;
    void handleSendMessage(question);
  };

  const handleWorkspaceResizeStart = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    const handleMouseMove = (moveEvent: MouseEvent) => {
      const nextMaxWidth = Math.min(Math.floor(window.innerWidth * 0.5), MAX_WORKSPACE_WIDTH);
      const nextWidth = window.innerWidth - moveEvent.clientX - 20;
      setWorkspaceWidth(Math.min(Math.max(nextWidth, MIN_WORKSPACE_WIDTH), nextMaxWidth));
    };
    const handleMouseUp = () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  }, []);

  const renderToolCall = (toolCall: SSEToolCallEvent, index: number) => {
    switch (toolCall.name) {
      case "render_chart":
        return <ChartAction key={index} args={toolCall.arguments as unknown as RenderChartArgs} />;
      case "render_table":
        return <TableAction key={index} args={toolCall.arguments as unknown as RenderTableArgs} />;
      case "show_notification":
        return <NotificationAction key={index} args={toolCall.arguments as unknown as ShowNotificationArgs} />;
      default:
        return null;
    }
  };

  return (
    <div
      className="chat-layout"
      style={{
        display: "flex",
        gap: "18px",
        height: "100vh",
        padding: `${TOP_SAFE_AREA}px 20px 20px`,
        boxSizing: "border-box",
        overflow: "hidden",
      }}
    >
      <section
        style={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          borderRadius: "30px",
          background: "linear-gradient(180deg, rgba(6, 8, 18, 0.78), rgba(11, 14, 24, 0.7))",
          border: "1px solid rgba(255, 255, 255, 0.08)",
          boxShadow: "0 24px 80px rgba(0, 0, 0, 0.35)",
          backdropFilter: "blur(18px)",
          overflow: "hidden",
        }}
      >
        <header
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "18px",
            padding: "22px 24px 18px",
            borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
          }}
        >
          <div>
            <h1 style={{ margin: 0, fontSize: "1.65rem", fontWeight: 700, letterSpacing: "-0.03em" }}>
              Agent Studio
            </h1>
            <p style={{ margin: "6px 0 0", color: "rgba(255, 255, 255, 0.56)", fontSize: "13px" }}>
              在同一视图里追踪对话、文件与运行痕迹，右侧展示当前会话的 workspace。
            </p>
          </div>
          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", justifyContent: "flex-end" }}>
            {!workspaceOpen ? (
              <button
                onClick={() => setWorkspaceOpen(true)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "8px 14px",
                  borderRadius: "999px",
                  border: "1px solid rgba(118, 165, 255, 0.24)",
                  background: "rgba(118, 165, 255, 0.12)",
                  color: "#f4f7ff",
                  cursor: "pointer",
                }}
              >
                <PanelRightOpen size={16} />
                打开 Workspace
              </button>
            ) : null}
            <button
              onClick={handleExportReport}
              disabled={messages.length === 0}
              title="导出为独立 HTML 报告"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 16px",
                borderRadius: "999px",
                border: "1px solid rgba(84, 112, 198, 0.5)",
                background:
                  messages.length === 0
                    ? "transparent"
                    : "linear-gradient(135deg, rgba(84,112,198,0.22), rgba(59,162,114,0.22))",
                color: messages.length === 0 ? "rgba(255,255,255,0.3)" : "rgba(255,255,255,0.92)",
                cursor: messages.length === 0 ? "not-allowed" : "pointer",
                opacity: messages.length === 0 ? 0.5 : 1,
              }}
            >
              <Download size={16} />
              导出报告
            </button>
            <button
              onClick={() => uploadInputRef.current?.click()}
              disabled={!sessionId || isUploading}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 16px",
                borderRadius: "999px",
                border: "1px solid rgba(255, 255, 255, 0.15)",
                background: "transparent",
                color: "rgba(255, 255, 255, 0.76)",
                cursor: !sessionId || isUploading ? "not-allowed" : "pointer",
                opacity: !sessionId || isUploading ? 0.5 : 1,
              }}
            >
              <FileUp size={16} />
              {isUploading ? "上传中..." : "上传文件"}
            </button>
            <input
              ref={uploadInputRef}
              type="file"
              multiple
              onChange={(event) => void handleUpload(event.target.files)}
              style={{ display: "none" }}
            />
            <button
              onClick={handleClearChat}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 16px",
                borderRadius: "999px",
                border: "1px solid rgba(255, 255, 255, 0.15)",
                background: "transparent",
                color: "rgba(255, 255, 255, 0.72)",
                cursor: "pointer",
              }}
            >
              <Trash2 size={16} />
              清空对话
            </button>
          </div>
        </header>

        {uploads.length > 0 ? (
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "8px",
              padding: "12px 24px 0",
            }}
          >
            {uploads.map((file) => (
              <span
                key={file.name}
                style={{
                  padding: "7px 11px",
                  borderRadius: "999px",
                  background: "rgba(255, 255, 255, 0.06)",
                  border: "1px solid rgba(255, 255, 255, 0.12)",
                  color: "rgba(255, 255, 255, 0.76)",
                  fontSize: "12px",
                }}
              >
                {file.name}
              </span>
            ))}
          </div>
        ) : null}

        <div style={{ flex: 1, minHeight: 0, padding: "16px 24px 24px", display: "flex", flexDirection: "column" }}>
          {centerMode === "file" ? (
            <FileViewer
              file={selectedWorkspaceFile}
              loading={workspacePreviewLoading}
              error={workspacePreviewError}
              onBack={() => setCenterMode("chat")}
              onRefresh={() => {
                if (selectedWorkspacePath) {
                  void loadWorkspaceFile(selectedWorkspacePath);
                }
              }}
            />
          ) : (
            <>
              <div
                className="messages-container"
                style={{
                  flex: 1,
                  minHeight: 0,
                  overflowY: "auto",
                  paddingRight: "8px",
                }}
              >
                {messages.length === 0 && !isLoading ? (
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      justifyContent: "center",
                      height: "100%",
                      color: "rgba(255, 255, 255, 0.5)",
                    }}
                  >
                    <FileUp size={48} style={{ marginBottom: "16px", opacity: 0.5 }} />
                    <p style={{ fontSize: "16px", margin: 0 }}>开始一段 Agent Studio 会话</p>
                    <p style={{ fontSize: "14px", margin: "8px 0 0" }}>
                      试试输入：「分析一下销售数据」或「打开 chat.log 看看刚才做了什么」
                    </p>
                  </div>
                ) : null}

                {messages.map((message) => (
                  <div key={message.id} className={`message ${message.role}`} style={{ marginBottom: "20px" }}>
                    {message.role === "user" ? (
                      <div style={{ display: "flex", justifyContent: "flex-end" }}>
                        <div
                          style={{
                            maxWidth: "82%",
                            padding: "14px 18px",
                            borderRadius: "18px 18px 4px 18px",
                            background: "linear-gradient(135deg, #5470c6, #3ba272)",
                            color: "#fff",
                            fontSize: "15px",
                            lineHeight: 1.5,
                          }}
                        >
                          {message.content}
                        </div>
                      </div>
                    ) : (
                      <div style={{ maxWidth: "100%" }}>
                        {message.thinking && message.thinking.length > 0 ? <ThinkingPanel steps={message.thinking} /> : null}
                        <div
                          style={{
                            padding: "16px 20px",
                            borderRadius: "18px 18px 18px 4px",
                            background: "rgba(255, 255, 255, 0.05)",
                            border: "1px solid rgba(255, 255, 255, 0.08)",
                          }}
                        >
                          <MarkdownRenderer content={message.content} />
                        </div>

                        {message.toolCalls && message.toolCalls.length > 0 ? (
                          <div style={{ marginTop: "12px" }}>
                            {message.toolCalls.map((toolCall, index) => renderToolCall(toolCall, index))}
                          </div>
                        ) : null}

                        {message.suggestedQuestions && message.suggestedQuestions.length > 0 && !isLoading ? (
                          <div
                            style={{
                              display: "flex",
                              flexWrap: "wrap",
                              gap: "8px",
                              marginTop: "14px",
                              animation: "fadeIn 0.4s ease-out",
                            }}
                          >
                            {message.suggestedQuestions.map((question, index) => (
                              <button
                                key={index}
                                onClick={() => handleSuggestionClick(question)}
                                style={{
                                  padding: "8px 16px",
                                  borderRadius: "999px",
                                  border: "1px solid rgba(84, 112, 198, 0.4)",
                                  background: "rgba(84, 112, 198, 0.08)",
                                  color: "rgba(255, 255, 255, 0.8)",
                                  fontSize: "13px",
                                  cursor: "pointer",
                                  lineHeight: 1.4,
                                }}
                              >
                                {question}
                              </button>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    )}
                  </div>
                ))}

                {isLoading && currentThinking.length > 0 ? (
                  <div style={{ marginBottom: "20px" }}>
                    <ThinkingPanel steps={currentThinking} isStreaming />
                  </div>
                ) : null}

                {isLoading && toolCalls.length > 0 ? (
                  <div style={{ marginBottom: "20px" }}>
                    {toolCalls.map((toolCall, index) => renderToolCall(toolCall, index))}
                  </div>
                ) : null}

                {isLoading && currentThinking.length === 0 ? (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      padding: "16px",
                      color: "rgba(255, 255, 255, 0.6)",
                    }}
                  >
                    <Loader2 size={16} style={{ animation: "spin 1s linear infinite" }} />
                    <span>正在思考...</span>
                  </div>
                ) : null}

                <div ref={messagesEndRef} />
              </div>

              <div
                className="input-area"
                style={{
                  paddingTop: "18px",
                  marginTop: "18px",
                  borderTop: "1px solid rgba(255, 255, 255, 0.08)",
                }}
              >
                <div style={{ display: "flex", gap: "12px", alignItems: "flex-end" }}>
                  <textarea
                    ref={inputRef}
                    value={inputValue}
                    onChange={(event) => setInputValue(event.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={sessionId ? "在 Agent Studio 中输入指令... (Enter 发送, Shift+Enter 换行)" : "正在初始化会话，请稍候..."}
                    disabled={isLoading || !sessionId}
                    rows={1}
                    style={{
                      flex: 1,
                      padding: "14px 18px",
                      borderRadius: "18px",
                      border: "1px solid rgba(255, 255, 255, 0.15)",
                      background: "rgba(255, 255, 255, 0.05)",
                      color: "#fff",
                      fontSize: "15px",
                      resize: "none",
                      outline: "none",
                      minHeight: "54px",
                      maxHeight: "150px",
                      fontFamily: "inherit",
                    }}
                  />
                  <button
                    onClick={() => void handleSendMessage()}
                    disabled={isLoading || !inputValue.trim() || !sessionId}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      width: "54px",
                      height: "54px",
                      borderRadius: "18px",
                      border: "none",
                      background:
                        isLoading || !inputValue.trim()
                          ? "rgba(255, 255, 255, 0.1)"
                          : "linear-gradient(135deg, #5470c6, #3ba272)",
                      color: isLoading || !inputValue.trim() ? "rgba(255, 255, 255, 0.3)" : "#fff",
                      cursor: isLoading || !inputValue.trim() ? "not-allowed" : "pointer",
                    }}
                  >
                    {isLoading ? (
                      <Loader2 size={20} style={{ animation: "spin 1s linear infinite" }} />
                    ) : (
                      <Send size={20} />
                    )}
                  </button>
                </div>
                <p
                  style={{
                    margin: "8px 0 0",
                    fontSize: "12px",
                    color: "rgba(255, 255, 255, 0.4)",
                    textAlign: "center",
                  }}
                >
                  Agent Studio 可能会生成不准确的信息，请核实重要内容
                </p>
              </div>
            </>
          )}
        </div>
      </section>

      {workspaceOpen ? (
        <>
          <WorkspaceResizeHandle onMouseDown={handleWorkspaceResizeStart} />
          <div
            style={{
              width: `${workspaceWidth}px`,
              minWidth: `${MIN_WORKSPACE_WIDTH}px`,
              maxWidth: `${Math.min(Math.floor(window.innerWidth * 0.5), MAX_WORKSPACE_WIDTH)}px`,
              flexShrink: 0,
            }}
          >
            <WorkspacePanel
              roots={workspaceRoots}
              loading={workspaceLoading}
              error={workspaceError}
              activeTab={workspaceTab}
              selectedPath={selectedWorkspacePath}
              previewFile={selectedWorkspaceFile}
              previewLoading={workspacePreviewLoading}
              previewError={workspacePreviewError}
              onTabChange={setWorkspaceTab}
              onSelectFile={(path) => void loadWorkspaceFile(path)}
              onOpenViewer={() => {
                if (selectedWorkspaceFile) {
                  setCenterMode("file");
                }
              }}
              onToggleOpen={() => setWorkspaceOpen(false)}
              onRefresh={() => {
                void refreshWorkspace();
                if (selectedWorkspacePath) {
                  void loadWorkspaceFile(selectedWorkspacePath);
                }
              }}
              currentRun={currentRun}
              currentTrajectory={currentTrajectory}
              currentEval={currentEval}
              currentArtifacts={currentArtifacts}
              sessionRuns={sessionRuns}
              globalRuns={globalRuns}
              runLoading={runLoading}
              activeRunId={activeRunId}
              onSelectRun={handleSelectRun}
              onOpenRunFile={(path) => {
                const runSession = currentRun?.session_id;
                void loadWorkspaceFile(path, {
                  targetSessionId: runSession !== sessionId ? runSession : undefined,
                });
              }}
            />
          </div>
        </>
      ) : null}

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .messages-container::-webkit-scrollbar {
          width: 6px;
        }
        .messages-container::-webkit-scrollbar-track {
          background: transparent;
        }
        .messages-container::-webkit-scrollbar-thumb {
          background: rgba(255, 255, 255, 0.2);
          border-radius: 3px;
        }
        textarea::-webkit-scrollbar {
          width: 4px;
        }
        textarea::-webkit-scrollbar-thumb {
          background: rgba(255, 255, 255, 0.2);
          border-radius: 2px;
        }
      `}</style>
    </div>
  );
}

export default ChatLayout;
