/**
 * ThinkingPanel - 折叠式思考过程组件
 * 
 * 展示 Agent 的思考过程、工具调用等中间步骤
 * 支持折叠/展开，类似 DeepSeek 的思考过程展示
 */
import { useState } from 'react';
import { ChevronDown, ChevronRight, Brain, Wrench, CheckCircle } from 'lucide-react';
import type { ThinkingStep } from '../types';

interface ThinkingPanelProps {
  steps: ThinkingStep[];
  isStreaming?: boolean;
}

// 去除 ANSI 颜色代码
const ANSI_ESCAPE_PATTERN = new RegExp(String.raw`\u001b\[[0-9;]*m`, 'g');
const stripAnsi = (str: string) => str.replace(ANSI_ESCAPE_PATTERN, '');

export function ThinkingPanel({ steps, isStreaming = false }: ThinkingPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (steps.length === 0) return null;

  const getStepIcon = (type: ThinkingStep['type']) => {
    switch (type) {
      case 'thinking':
        return <Brain size={14} />;
      case 'tool_call':
        return <Wrench size={14} />;
      case 'tool_result':
        return <CheckCircle size={14} />;
      default:
        return <Brain size={14} />;
    }
  };

  const getStepLabel = (type: ThinkingStep['type']) => {
    switch (type) {
      case 'thinking':
        return '思考中';
      case 'tool_call':
        return '调用工具';
      case 'tool_result':
        return '工具结果';
      default:
        return '处理中';
    }
  };

  return (
    <div className="thinking-panel" style={{
      background: 'rgba(255, 255, 255, 0.03)',
      borderRadius: '12px',
      border: '1px solid rgba(255, 255, 255, 0.08)',
      marginBottom: '12px',
      overflow: 'hidden',
    }}>
      {/* 折叠头部 */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '12px 16px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          color: 'rgba(255, 255, 255, 0.7)',
          fontSize: '13px',
          textAlign: 'left',
        }}
      >
        {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <Brain size={16} style={{ color: '#91cc75' }} />
        <span>
          {isStreaming ? '正在思考...' : `思考过程 (${steps.length} 步)`}
        </span>
        {isStreaming && (
          <span className="thinking-dots" style={{
            display: 'inline-flex',
            gap: '2px',
          }}>
            <span style={{ animation: 'pulse 1s infinite' }}>•</span>
            <span style={{ animation: 'pulse 1s infinite 0.2s' }}>•</span>
            <span style={{ animation: 'pulse 1s infinite 0.4s' }}>•</span>
          </span>
        )}
      </button>

      {/* 展开的内容 */}
      {isExpanded && (
        <div style={{
          borderTop: '1px solid rgba(255, 255, 255, 0.05)',
          padding: '12px 16px',
          maxHeight: '300px',
          overflowY: 'auto',
        }}>
          {steps.map((step) => (
            <div
              key={step.id}
              style={{
                display: 'flex',
                gap: '10px',
                padding: '8px 0',
                borderBottom: '1px solid rgba(255, 255, 255, 0.03)',
              }}
            >
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '24px',
                height: '24px',
                borderRadius: '6px',
                background: 'rgba(255, 255, 255, 0.05)',
                color: step.type === 'thinking' ? '#91cc75' : 
                       step.type === 'tool_call' ? '#5470c6' : '#fac858',
                flexShrink: 0,
              }}>
                {getStepIcon(step.type)}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: '11px',
                  color: 'rgba(255, 255, 255, 0.5)',
                  marginBottom: '4px',
                }}>
                  {getStepLabel(step.type)}
                </div>
                <div style={{
                  fontSize: '13px',
                  color: 'rgba(255, 255, 255, 0.85)',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  fontFamily: step.type === 'tool_result' 
                    ? '"SF Mono", "SFMono-Regular", ui-monospace, monospace' 
                    : 'inherit',
                }}>
                  {stripAnsi(step.content)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default ThinkingPanel;
