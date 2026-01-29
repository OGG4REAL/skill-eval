/**
 * CopilotApp - AI 助手应用
 * 
 * Phase 3: DeepSeek 风格的全屏对话 UI
 * 
 * 注意：暂时不使用 CopilotKit Provider 包裹，因为：
 * 1. ChatLayout 是完全手写的 fetch + SSE 解析逻辑
 * 2. 不依赖 CopilotKit 的 useCopilotChat hooks
 * 3. 后续如果需要 useCopilotReadable 等功能，再集成 CopilotKit 标准协议
 */
import { useEffect, useState, useCallback } from 'react';
import { ChatLayout } from './copilot';
import { createSession, listSessions } from './lib/api';
import type { SessionSummary } from './types';
import './App.css';

export default function CopilotApp() {
  // 从 URL 或 localStorage 获取 session_id
  const getSessionId = () => {
    const urlParams = new URLSearchParams(window.location.search);
    const urlSessionId = urlParams.get('session');
    if (urlSessionId) {
      localStorage.setItem('copilot_session_id', urlSessionId);
      return urlSessionId;
    }
    return localStorage.getItem('copilot_session_id') || undefined;
  };

  const [sessionId, setSessionId] = useState<string | undefined>(() => getSessionId());
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [showSessionPicker, setShowSessionPicker] = useState(false);

  // 加载会话列表
  const loadSessions = useCallback(async () => {
    try {
      const list = await listSessions();
      setSessions(list);
    } catch (error) {
      console.error('加载会话列表失败:', error);
    }
  }, []);

  // 首次加载会话列表
  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // 如果没有 sessionId，创建新会话
  useEffect(() => {
    if (sessionId) return;
    let active = true;
    createSession()
      .then((id) => {
        if (!active) return;
        localStorage.setItem('copilot_session_id', id);
        setSessionId(id);
        loadSessions(); // 刷新列表
      })
      .catch((error) => {
        console.error('创建会话失败:', error);
      });
    return () => {
      active = false;
    };
  }, [sessionId, loadSessions]);

  // 切换会话
  const handleSwitchSession = (newSessionId: string) => {
    localStorage.setItem('copilot_session_id', newSessionId);
    setSessionId(newSessionId);
    setShowSessionPicker(false);
    // 刷新页面以清空前端状态
    window.location.reload();
  };

  // 创建新会话
  const handleNewSession = async () => {
    try {
      const newId = await createSession();
      localStorage.setItem('copilot_session_id', newId);
      setSessionId(newId);
      setShowSessionPicker(false);
      loadSessions();
      // 刷新页面以清空前端状态
      window.location.reload();
    } catch (error) {
      console.error('创建会话失败:', error);
    }
  };

  // 格式化 session ID 显示（截取前8位）
  const formatSessionId = (id: string) => id.slice(0, 8);

  return (
    <div className="copilot-app" style={{
      minHeight: '100vh',
      background: 'radial-gradient(circle at top, #2b2f77 0%, #05050a 55%)',
      position: 'relative',
    }}>
      {/* Session 选择器按钮 - 固定在左上角 */}
      <div style={{
        position: 'fixed',
        top: '20px',
        left: '20px',
        zIndex: 1000,
      }}>
        <button
          onClick={() => setShowSessionPicker(!showSessionPicker)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 14px',
            borderRadius: '10px',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            background: 'rgba(0, 0, 0, 0.4)',
            backdropFilter: 'blur(10px)',
            color: 'rgba(255, 255, 255, 0.8)',
            cursor: 'pointer',
            fontSize: '13px',
            fontFamily: 'monospace',
          }}
        >
          <span style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: '#4ade80',
          }} />
          {sessionId ? formatSessionId(sessionId) : '加载中...'}
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>

        {/* Session 下拉菜单 */}
        {showSessionPicker && (
          <>
            {/* 点击外部关闭 */}
            <div
              onClick={() => setShowSessionPicker(false)}
              style={{
                position: 'fixed',
                inset: 0,
                zIndex: 998,
              }}
            />
            <div style={{
              position: 'absolute',
              top: '100%',
              left: 0,
              marginTop: '8px',
              minWidth: '240px',
              maxHeight: '320px',
              overflowY: 'auto',
              padding: '8px',
              borderRadius: '12px',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              background: 'rgba(20, 20, 30, 0.95)',
              backdropFilter: 'blur(20px)',
              boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
              zIndex: 999,
            }}>
              {/* 新建会话按钮 */}
              <button
                onClick={handleNewSession}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  padding: '10px 12px',
                  borderRadius: '8px',
                  border: 'none',
                  background: 'linear-gradient(135deg, #5470c6, #3ba272)',
                  color: '#fff',
                  cursor: 'pointer',
                  fontSize: '13px',
                  fontWeight: 500,
                  marginBottom: '8px',
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                新建会话
              </button>

              {/* 分隔线 */}
              <div style={{
                height: '1px',
                background: 'rgba(255, 255, 255, 0.1)',
                margin: '8px 0',
              }} />

              {/* 会话列表 */}
              <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.4)', padding: '4px 12px', marginBottom: '4px' }}>
                历史会话 ({sessions.length})
              </div>
              {sessions.length === 0 ? (
                <div style={{
                  padding: '12px',
                  color: 'rgba(255, 255, 255, 0.4)',
                  fontSize: '13px',
                  textAlign: 'center',
                }}>
                  暂无历史会话
                </div>
              ) : (
                sessions.map((session) => (
                  <button
                    key={session.session_id}
                    onClick={() => handleSwitchSession(session.session_id)}
                    style={{
                      width: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px',
                      padding: '10px 12px',
                      borderRadius: '8px',
                      border: 'none',
                      background: session.session_id === sessionId
                        ? 'rgba(84, 112, 198, 0.3)'
                        : 'transparent',
                      color: session.session_id === sessionId
                        ? '#fff'
                        : 'rgba(255, 255, 255, 0.7)',
                      cursor: 'pointer',
                      fontSize: '13px',
                      textAlign: 'left',
                      transition: 'background 0.15s',
                    }}
                    onMouseEnter={(e) => {
                      if (session.session_id !== sessionId) {
                        e.currentTarget.style.background = 'rgba(255, 255, 255, 0.08)';
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (session.session_id !== sessionId) {
                        e.currentTarget.style.background = 'transparent';
                      }
                    }}
                  >
                    <span style={{
                      width: '6px',
                      height: '6px',
                      borderRadius: '50%',
                      background: session.session_id === sessionId ? '#4ade80' : 'rgba(255,255,255,0.3)',
                      flexShrink: 0,
                    }} />
                    <span style={{ fontFamily: 'monospace' }}>
                      {formatSessionId(session.session_id)}
                    </span>
                    {session.session_id === sessionId && (
                      <span style={{
                        marginLeft: 'auto',
                        fontSize: '11px',
                        color: 'rgba(255,255,255,0.5)',
                      }}>
                        当前
                      </span>
                    )}
                  </button>
                ))
              )}
            </div>
          </>
        )}
      </div>

      <ChatLayout sessionId={sessionId} />
    </div>
  );
}
