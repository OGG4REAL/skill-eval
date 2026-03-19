import { useEffect, useState, useRef } from "react";
import type { ComponentProps } from "react";
import "./App.css";
import {
  createSession,
  listSessions,
  listUploads,
  openLogStream,
  sendMessage,
  uploadFiles,
} from "./lib/api";
import type { FileInfo, SessionSummary } from "./types";
import { ChartRenderer } from "./components/ChartRenderer";

function formatBytes(size: number) {
  if (!size) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(size) / Math.log(1024));
  return `${(size / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

// 去除 ANSI 颜色代码
const ANSI_ESCAPE_PATTERN = new RegExp(String.raw`\u001b\[[0-9;]*m`, "g");
const stripAnsi = (str: string) => str.replace(ANSI_ESCAPE_PATTERN, "");

type ChartData = ComponentProps<typeof ChartRenderer>["charts"][number];

interface AnalysisSummary {
  rows: number;
  cols: number;
  missing_cells: number;
  missing_pct: number;
}

interface AnalysisResult {
  summary: AnalysisSummary;
  columns: Array<Record<string, unknown>>;
  charts: ChartData[];
}

export default function App() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const [uploads, setUploads] = useState<FileInfo[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  
  // 使用 useRef 而不是 useState 来避免闭包问题
  const eventSourceRef = useRef<EventSource | null>(null);
  const jsonBufferRef = useRef("");
  const isCollectingJsonRef = useRef(false);
  const hasResultRef = useRef(false); // 标记是否已成功解析过结果
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listSessions().then(setSessions).catch(console.error);
  }, []);

  useEffect(() => {
    setLogs([]);
    setAnalysisResult(null);
    jsonBufferRef.current = "";
    isCollectingJsonRef.current = false;
    hasResultRef.current = false; // 重置结果标记
    eventSourceRef.current?.close();
    
    if (!selectedSession) return;
    
    listUploads(selectedSession).then(setUploads).catch(console.error);
    
    const es = openLogStream(selectedSession, (line) => {
      const cleanLine = stripAnsi(line);
      
      // Check for analysis markers - 必须是独立的一行，不能是代码的一部分
      // 排除包含 print( 或引号的行（这些是代码行）
      const isCodeLine = cleanLine.includes('print(') || cleanLine.includes('"ANALYSIS_RESULT');
      
      if (!isCodeLine && cleanLine.trim() === "ANALYSIS_RESULT_START") {
        // 如果已经有结果了，跳过后续的 ANALYSIS_RESULT 块
        if (!hasResultRef.current) {
          isCollectingJsonRef.current = true;
          jsonBufferRef.current = "";
        }
        return;
      }
      
      if (!isCodeLine && cleanLine.trim() === "ANALYSIS_RESULT_END") {
        if (isCollectingJsonRef.current) {
          isCollectingJsonRef.current = false;
          try {
            const jsonStr = jsonBufferRef.current.trim();
            // 确保 JSON 以 { 开头且以 } 结尾（完整的 JSON）
            if (jsonStr && jsonStr.startsWith('{') && jsonStr.endsWith('}')) {
              const result = JSON.parse(jsonStr);
              console.log("✅ Analysis Result Parsed:", result);
              setAnalysisResult(result);
              hasResultRef.current = true; // 标记已成功解析
            }
          } catch (e) {
            console.error("❌ Failed to parse analysis result:", e);
            console.log("Buffer content (first 500 chars):", jsonBufferRef.current.substring(0, 500));
          }
        }
        return;
      }
      
      if (isCollectingJsonRef.current) {
        jsonBufferRef.current += cleanLine + "\n";
      } else {
        setLogs((prev) => [...prev.slice(-500), cleanLine]);
      }
    });
    
    eventSourceRef.current = es;
    return () => {
      es.close();
      if (eventSourceRef.current === es) {
        eventSourceRef.current = null;
      }
    };
  }, [selectedSession]);

  // 自动滚动日志
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const handleCreateSession = async () => {
    const id = await createSession();
    const next = await listSessions();
    setSessions(next);
    setSelectedSession(id);
  };

  const handleUpload = async (files: FileList | null) => {
    if (!files || !selectedSession) return;
    await uploadFiles(selectedSession, Array.from(files));
    setUploads(await listUploads(selectedSession));
  };

  const handleSend = async () => {
    if (!message.trim() || !selectedSession) return;
    setIsSending(true);
    setAnalysisResult(null); // Clear previous results
    try {
      await sendMessage(selectedSession, message.trim());
      setMessage("");
    } catch (e) {
      console.error(e);
      alert("发送失败，请检查控制台");
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar glass-card">
        <div className="sidebar-header">
          <h1>数据工作室</h1>
          <p>Apple 风格的 CSV Agent 前端</p>
          <button onClick={handleCreateSession}>＋ 新建会话</button>
        </div>
        <div className="session-list">
          {sessions.map((session) => (
            <div
              key={session.session_id}
              className={`session-item ${
                session.session_id === selectedSession ? "active" : ""
              }`}
              onClick={() => setSelectedSession(session.session_id)}
            >
              <span>{session.session_id}</span>
            </div>
          ))}
          {sessions.length === 0 && <p>暂无会话，点击上方按钮创建。</p>}
        </div>
        <div className="uploads">
          <h2>上传文件</h2>
          <label className="upload-drop">
            <input type="file" multiple onChange={(e) => handleUpload(e.target.files)} />
            <span>拖拽或点击上传 CSV / Excel</span>
          </label>
          <div className="file-list">
            {uploads.map((file) => (
              <div key={file.name} className="file-row">
                <span>{file.name}</span>
                <span>{formatBytes(file.size)}</span>
              </div>
            ))}
            {uploads.length === 0 && <p>尚未上传文件</p>}
          </div>
        </div>
      </aside>

      <main className="content-area" style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 64px)', overflow: 'hidden' }}>
        <section className="glass-card chat-panel" style={{ flex: '0 0 40%', display: 'flex', flexDirection: 'column', minHeight: '300px', marginBottom: '12px', overflow: 'hidden' }}>
          <div className="chat-header">
      <div>
              <h2>{selectedSession ?? "未选择会话"}</h2>
              <p>实时日志 / Agent 思考过程</p>
            </div>
          </div>
          <div className="log-stream" style={{ flex: 1, overflowY: 'auto', margin: '12px 0', padding: '10px', background: 'rgba(0,0,0,0.2)', borderRadius: '12px' }}>
            {logs.map((line, idx) => (
              <p key={`${line}-${idx}`} style={{ margin: '4px 0', wordBreak: 'break-all', fontSize: '13px' }}>{line}</p>
            ))}
            <div ref={logEndRef} />
            {logs.length === 0 && <p className="placeholder">暂无日志，请先选择会话</p>}
      </div>
          <div className="chat-input" style={{ marginTop: 'auto' }}>
            <input
              type="text"
              placeholder="输入指令，例如：分析 showcase_financial_pl_data.csv"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              disabled={!selectedSession}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
            />
            <button onClick={handleSend} disabled={isSending || !selectedSession}>
              {isSending ? "启动中..." : "发送"}
        </button>
          </div>
        </section>

        <section className="glass-card outputs-panel" style={{ flex: '1', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div className="outputs-header" style={{ padding: '20px 20px 0' }}>
            <h2>分析结果</h2>
            <p style={{ margin: '4px 0' }}>基于 JSON 数据的动态渲染</p>
          </div>
          
          <div className="analysis-content" style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
            {analysisResult ? (
              <div style={{ width: '100%' }}>
                {/* 统计摘要 */}
                <div className="summary-grid" style={{ 
                  display: 'grid', 
                  gridTemplateColumns: 'repeat(4, 1fr)', 
                  gap: '15px', 
                  marginBottom: '30px' 
                }}>
                  <div className="stat-card glass-card" style={{ padding: '15px', textAlign: 'center' }}>
                    <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{analysisResult.summary.rows}</div>
                    <div style={{ color: '#666', fontSize: '12px' }}>总行数</div>
                  </div>
                  <div className="stat-card glass-card" style={{ padding: '15px', textAlign: 'center' }}>
                    <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{analysisResult.summary.cols}</div>
                    <div style={{ color: '#666', fontSize: '12px' }}>总列数</div>
                  </div>
                  <div className="stat-card glass-card" style={{ padding: '15px', textAlign: 'center' }}>
                    <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{analysisResult.summary.missing_cells}</div>
                    <div style={{ color: '#666', fontSize: '12px' }}>缺失值</div>
                  </div>
                  <div className="stat-card glass-card" style={{ padding: '15px', textAlign: 'center' }}>
                    <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{analysisResult.summary.missing_pct}%</div>
                    <div style={{ color: '#666', fontSize: '12px' }}>缺失率</div>
                  </div>
                </div>

                {/* 图表渲染 */}
                <ChartRenderer charts={analysisResult.charts} />
              </div>
            ) : (
              <p className="placeholder">暂无分析结果，请发送指令开始分析。</p>
            )}
          </div>
        </section>
      </main>
      </div>
  );
}
