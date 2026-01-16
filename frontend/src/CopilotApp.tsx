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
import { ChatLayout } from './copilot';
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

  const sessionId = getSessionId();

  return (
    <div className="copilot-app" style={{
      minHeight: '100vh',
      background: 'radial-gradient(circle at top, #2b2f77 0%, #05050a 55%)',
    }}>
      <ChatLayout sessionId={sessionId} />
    </div>
  );
}
