/**
 * ChatLayout - DeepSeek 风格的全屏对话布局
 * 
 * 支持流式对话、思考过程展示和 Generative UI
 * 注意：使用自定义 SSE 协议而非 CopilotKit 标准协议
 */
import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Trash2, FileUp, Loader2, Download } from 'lucide-react';
import { ThinkingPanel, MarkdownRenderer } from './components';
import { ChartAction, TableAction, NotificationAction } from './actions';
import { listUploads, uploadFiles } from '../lib/api';
import { downloadReport } from '../lib/reportGenerator';
import type { FileInfo } from '../types';
import type { 
  ChatMessage, 
  ThinkingStep, 
  RenderChartArgs, 
  RenderTableArgs, 
  ShowNotificationArgs,
  SSEToolCallEvent 
} from './types';

// 生成唯一 ID
const generateId = () => `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

interface ChatLayoutProps {
  sessionId?: string;
}

export function ChatLayout({ sessionId }: ChatLayoutProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [currentThinking, setCurrentThinking] = useState<ThinkingStep[]>([]);
  const [toolCalls, setToolCalls] = useState<SSEToolCallEvent[]>([]);
  const [uploads, setUploads] = useState<FileInfo[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const uploadInputRef = useRef<HTMLInputElement>(null);

  // 滚动到底部
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, currentThinking, scrollToBottom]);

  useEffect(() => {
    if (!sessionId) return;
    listUploads(sessionId)
      .then(setUploads)
      .catch(() => setUploads([]));
  }, [sessionId]);

  // 发送消息
  const handleSendMessage = async () => {
    const trimmedInput = inputValue.trim();
    if (!trimmedInput || isLoading || !sessionId) return;

    // 添加用户消息
    const userMessage: ChatMessage = {
      id: generateId(),
      role: 'user',
      content: trimmedInput,
      timestamp: Date.now(),
    };
    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);
    setCurrentThinking([]);
    setToolCalls([]);

    try {
      // 调用后端 SSE 接口
      const response = await fetch('/copilotkit/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          messages: [...messages, userMessage].map(m => ({
            role: m.role,
            content: m.content,
          })),
          session_id: sessionId,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let assistantContent = '';
      const thinkingSteps: ThinkingStep[] = [];
      const collectedToolCalls: SSEToolCallEvent[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            // 解析 SSE 事件类型
            continue;
          }
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              
              if (data.type === 'thinking') {
                const step: ThinkingStep = {
                  id: generateId(),
                  type: 'thinking',
                  content: data.content,
                  timestamp: Date.now(),
                };
                thinkingSteps.push(step);
                setCurrentThinking([...thinkingSteps]);
              } else if (data.type === 'tool_call') {
                const step: ThinkingStep = {
                  id: generateId(),
                  type: 'tool_call',
                  content: data.content,
                  timestamp: Date.now(),
                };
                thinkingSteps.push(step);
                setCurrentThinking([...thinkingSteps]);
              } else if (data.type === 'tool_result') {
                const step: ThinkingStep = {
                  id: generateId(),
                  type: 'tool_result',
                  content: data.content,
                  timestamp: Date.now(),
                };
                thinkingSteps.push(step);
                setCurrentThinking([...thinkingSteps]);
              } else if (data.type === 'response') {
                assistantContent = data.content;
              } else if (data.name) {
                // 客户端工具调用
                collectedToolCalls.push({
                  name: data.name,
                  arguments: data.arguments,
                });
                setToolCalls([...collectedToolCalls]);
              }
            } catch {
              // 忽略解析错误
            }
          }
        }
      }

      // 添加助手消息
      const assistantMessage: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: assistantContent,
        thinking: thinkingSteps,
        toolCalls: collectedToolCalls,
        timestamp: Date.now(),
      };
      setMessages(prev => [...prev, assistantMessage]);
      setCurrentThinking([]);

    } catch (error) {
      console.error('Failed to send message:', error);
      // 添加错误消息
      const errorMessage: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: `抱歉，发生了错误：${error instanceof Error ? error.message : '未知错误'}`,
        timestamp: Date.now(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  // 处理键盘事件
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // 导出报告
  const handleExportReport = () => {
    if (!sessionId || messages.length === 0) return;
    downloadReport(sessionId, messages);
  };

  // 清空对话
  const handleClearChat = () => {
    setMessages([]);
    setCurrentThinking([]);
    setToolCalls([]);
  };

  const handleUpload = async (files: FileList | null) => {
    if (!files || !sessionId) return;
    setIsUploading(true);
    try {
      await uploadFiles(sessionId, Array.from(files));
      const nextUploads = await listUploads(sessionId);
      setUploads(nextUploads);
    } catch (error) {
      console.error('上传失败:', error);
    } finally {
      setIsUploading(false);
    }
  };

  // 渲染工具调用结果
  const renderToolCall = (toolCall: SSEToolCallEvent, index: number) => {
    switch (toolCall.name) {
      case 'render_chart':
        return <ChartAction key={index} args={toolCall.arguments as unknown as RenderChartArgs} />;
      case 'render_table':
        return <TableAction key={index} args={toolCall.arguments as unknown as RenderTableArgs} />;
      case 'show_notification':
        return <NotificationAction key={index} args={toolCall.arguments as unknown as ShowNotificationArgs} />;
      default:
        return null;
    }
  };

  return (
    <div className="chat-layout" style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      maxWidth: '900px',
      margin: '0 auto',
      padding: '0 20px',
    }}>
      {/* 头部 */}
      <header style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '20px 0',
        borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
      }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 600 }}>
            CSV Data Summarizer
          </h1>
          <p style={{ margin: '4px 0 0', color: 'rgba(255, 255, 255, 0.6)', fontSize: '14px' }}>
            AI 驱动的数据分析助手
          </p>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
          <button
            onClick={handleExportReport}
            disabled={messages.length === 0}
            title="导出为独立 HTML 报告"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 16px',
              borderRadius: '10px',
              border: '1px solid rgba(84, 112, 198, 0.5)',
              background: messages.length === 0
                ? 'transparent'
                : 'linear-gradient(135deg, rgba(84,112,198,0.25), rgba(59,162,114,0.25))',
              color: messages.length === 0 ? 'rgba(255,255,255,0.3)' : 'rgba(255,255,255,0.9)',
              cursor: messages.length === 0 ? 'not-allowed' : 'pointer',
              fontSize: '14px',
              opacity: messages.length === 0 ? 0.5 : 1,
              transition: 'all 0.2s ease',
            }}
          >
            <Download size={16} />
            导出报告
          </button>
          <button
            onClick={() => uploadInputRef.current?.click()}
            disabled={!sessionId || isUploading}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 16px',
              borderRadius: '10px',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              background: 'transparent',
              color: 'rgba(255, 255, 255, 0.7)',
              cursor: !sessionId || isUploading ? 'not-allowed' : 'pointer',
              fontSize: '14px',
              opacity: !sessionId || isUploading ? 0.5 : 1,
            }}
          >
            <FileUp size={16} />
            {isUploading ? '上传中...' : '上传文件'}
          </button>
          <input
            ref={uploadInputRef}
            type="file"
            multiple
            onChange={(e) => handleUpload(e.target.files)}
            style={{ display: 'none' }}
          />
          <button
            onClick={handleClearChat}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 16px',
              borderRadius: '10px',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              background: 'transparent',
              color: 'rgba(255, 255, 255, 0.7)',
              cursor: 'pointer',
              fontSize: '14px',
            }}
          >
            <Trash2 size={16} />
            清空对话
          </button>
        </div>
      </header>

      {uploads.length > 0 && (
        <div style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '8px',
          padding: '12px 0 0',
        }}>
          {uploads.map((file) => (
            <span
              key={file.name}
              style={{
                padding: '6px 10px',
                borderRadius: '999px',
                background: 'rgba(255, 255, 255, 0.08)',
                border: '1px solid rgba(255, 255, 255, 0.12)',
                color: 'rgba(255, 255, 255, 0.75)',
                fontSize: '12px',
              }}
            >
              {file.name}
            </span>
          ))}
        </div>
      )}

      {/* 消息列表 */}
      <div className="messages-container" style={{
        flex: 1,
        overflowY: 'auto',
        padding: '20px 0',
      }}>
        {messages.length === 0 && !isLoading && (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            color: 'rgba(255, 255, 255, 0.5)',
          }}>
            <FileUp size={48} style={{ marginBottom: '16px', opacity: 0.5 }} />
            <p style={{ fontSize: '16px', margin: 0 }}>开始与 AI 助手对话</p>
            <p style={{ fontSize: '14px', margin: '8px 0 0' }}>
              试试问：「分析一下销售数据」或「生成收入趋势图表」
            </p>
          </div>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={`message ${message.role}`}
            style={{
              marginBottom: '20px',
            }}
          >
            {/* 用户消息 */}
            {message.role === 'user' && (
              <div style={{
                display: 'flex',
                justifyContent: 'flex-end',
              }}>
                <div style={{
                  maxWidth: '80%',
                  padding: '14px 18px',
                  borderRadius: '18px 18px 4px 18px',
                  background: 'linear-gradient(135deg, #5470c6, #3ba272)',
                  color: '#fff',
                  fontSize: '15px',
                  lineHeight: 1.5,
                }}>
                  {message.content}
                </div>
              </div>
            )}

            {/* 助手消息 */}
            {message.role === 'assistant' && (
              <div style={{
                maxWidth: '100%',
              }}>
                {/* 思考过程 */}
                {message.thinking && message.thinking.length > 0 && (
                  <ThinkingPanel steps={message.thinking} />
                )}
                
                {/* 消息内容 */}
                <div style={{
                  padding: '16px 20px',
                  borderRadius: '18px 18px 18px 4px',
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                }}>
                  <MarkdownRenderer content={message.content} />
                </div>

                {/* 工具调用结果（Generative UI）*/}
                {message.toolCalls && message.toolCalls.length > 0 && (
                  <div style={{ marginTop: '12px' }}>
                    {message.toolCalls.map((toolCall, index) => renderToolCall(toolCall, index))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {/* 加载中的思考过程 */}
        {isLoading && currentThinking.length > 0 && (
          <div style={{ marginBottom: '20px' }}>
            <ThinkingPanel steps={currentThinking} isStreaming />
          </div>
        )}

        {/* 实时工具调用 */}
        {isLoading && toolCalls.length > 0 && (
          <div style={{ marginBottom: '20px' }}>
            {toolCalls.map((toolCall, index) => renderToolCall(toolCall, index))}
          </div>
        )}

        {/* 加载指示器 */}
        {isLoading && currentThinking.length === 0 && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '16px',
            color: 'rgba(255, 255, 255, 0.6)',
          }}>
            <Loader2 size={16} className="spin" style={{ animation: 'spin 1s linear infinite' }} />
            <span>正在思考...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 输入区域 */}
      <div className="input-area" style={{
        padding: '20px 0',
        borderTop: '1px solid rgba(255, 255, 255, 0.08)',
      }}>
        <div style={{
          display: 'flex',
          gap: '12px',
          alignItems: 'flex-end',
        }}>
          <textarea
            ref={inputRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={sessionId ? "输入您的问题... (Enter 发送, Shift+Enter 换行)" : "会话初始化中，请稍候..."}
            disabled={isLoading || !sessionId}
            rows={1}
            style={{
              flex: 1,
              padding: '14px 18px',
              borderRadius: '16px',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              background: 'rgba(255, 255, 255, 0.05)',
              color: '#fff',
              fontSize: '15px',
              resize: 'none',
              outline: 'none',
              minHeight: '52px',
              maxHeight: '150px',
              fontFamily: 'inherit',
            }}
          />
          <button
            onClick={handleSendMessage}
            disabled={isLoading || !inputValue.trim() || !sessionId}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '52px',
              height: '52px',
              borderRadius: '16px',
              border: 'none',
              background: isLoading || !inputValue.trim() 
                ? 'rgba(255, 255, 255, 0.1)' 
                : 'linear-gradient(135deg, #5470c6, #3ba272)',
              color: isLoading || !inputValue.trim() 
                ? 'rgba(255, 255, 255, 0.3)' 
                : '#fff',
              cursor: isLoading || !inputValue.trim() ? 'not-allowed' : 'pointer',
              transition: 'all 0.2s ease',
            }}
          >
            {isLoading ? (
              <Loader2 size={20} style={{ animation: 'spin 1s linear infinite' }} />
            ) : (
              <Send size={20} />
            )}
          </button>
        </div>
        <p style={{
          margin: '8px 0 0',
          fontSize: '12px',
          color: 'rgba(255, 255, 255, 0.4)',
          textAlign: 'center',
        }}>
          AI 可能会产生不准确的信息，请核实重要内容
        </p>
      </div>

      {/* 全局动画样式 */}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes pulse {
          0%, 100% { opacity: 0.3; }
          50% { opacity: 1; }
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
