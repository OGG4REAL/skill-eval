/**
 * MarkdownRenderer - Markdown 渲染组件
 * 
 * 将 Markdown 文本渲染为 React 组件
 * 支持代码高亮、表格、链接等
 */
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';

interface MarkdownRendererProps {
  content: string;
}

function sanitizeLinkHref(href?: string): string | undefined {
  const trimmed = href?.trim();
  if (!trimmed) return undefined;

  const hasExplicitScheme = /^[a-zA-Z][a-zA-Z\d+.-]*:/.test(trimmed);
  if (!hasExplicitScheme) return trimmed;

  try {
    const parsed = new URL(trimmed);
    return ['http:', 'https:', 'mailto:'].includes(parsed.protocol) ? trimmed : undefined;
  } catch {
    return undefined;
  }
}

// 自定义组件样式
const components: Components = {
  // 代码块
  code({ className, children, ...props }) {
    const isInline = !className;
    
    if (isInline) {
      return (
        <code
          style={{
            background: 'rgba(255, 255, 255, 0.1)',
            padding: '2px 6px',
            borderRadius: '4px',
            fontSize: '0.9em',
            fontFamily: '"SF Mono", "SFMono-Regular", ui-monospace, monospace',
          }}
          {...props}
        >
          {children}
        </code>
      );
    }

    return (
      <pre
        style={{
          background: 'rgba(0, 0, 0, 0.3)',
          padding: '16px',
          borderRadius: '8px',
          overflow: 'auto',
          margin: '12px 0',
        }}
      >
        <code
          className={className}
          style={{
            fontFamily: '"SF Mono", "SFMono-Regular", ui-monospace, monospace',
            fontSize: '13px',
            lineHeight: 1.5,
          }}
          {...props}
        >
          {children}
        </code>
      </pre>
    );
  },

  // 表格
  table({ children }) {
    return (
      <div style={{ overflowX: 'auto', margin: '12px 0' }}>
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: '14px',
          }}
        >
          {children}
        </table>
      </div>
    );
  },

  th({ children }) {
    return (
      <th
        style={{
          padding: '10px 12px',
          textAlign: 'left',
          borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
          color: 'rgba(255, 255, 255, 0.7)',
          fontWeight: 500,
        }}
      >
        {children}
      </th>
    );
  },

  td({ children }) {
    return (
      <td
        style={{
          padding: '10px 12px',
          borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
          color: 'rgba(255, 255, 255, 0.9)',
        }}
      >
        {children}
      </td>
    );
  },

  // 链接
  a({ href, children }) {
    const safeHref = sanitizeLinkHref(href);
    if (!safeHref) {
      return <span>{children}</span>;
    }

    return (
      <a
        href={safeHref}
        target="_blank"
        rel="noopener noreferrer"
        style={{
          color: '#5470c6',
          textDecoration: 'none',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.textDecoration = 'underline';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.textDecoration = 'none';
        }}
      >
        {children}
      </a>
    );
  },

  // 标题
  h1({ children }) {
    return (
      <h1 style={{ fontSize: '1.5em', fontWeight: 600, margin: '16px 0 8px', color: '#fff' }}>
        {children}
      </h1>
    );
  },

  h2({ children }) {
    return (
      <h2 style={{ fontSize: '1.3em', fontWeight: 600, margin: '14px 0 8px', color: '#fff' }}>
        {children}
      </h2>
    );
  },

  h3({ children }) {
    return (
      <h3 style={{ fontSize: '1.1em', fontWeight: 600, margin: '12px 0 6px', color: '#fff' }}>
        {children}
      </h3>
    );
  },

  // 段落
  p({ children }) {
    return (
      <p style={{ margin: '8px 0', lineHeight: 1.6 }}>
        {children}
      </p>
    );
  },

  // 列表
  ul({ children }) {
    return (
      <ul style={{ margin: '8px 0', paddingLeft: '20px' }}>
        {children}
      </ul>
    );
  },

  ol({ children }) {
    return (
      <ol style={{ margin: '8px 0', paddingLeft: '20px' }}>
        {children}
      </ol>
    );
  },

  li({ children }) {
    return (
      <li style={{ margin: '4px 0', lineHeight: 1.5 }}>
        {children}
      </li>
    );
  },

  // 引用
  blockquote({ children }) {
    return (
      <blockquote
        style={{
          borderLeft: '3px solid rgba(255, 255, 255, 0.3)',
          paddingLeft: '16px',
          margin: '12px 0',
          color: 'rgba(255, 255, 255, 0.7)',
        }}
      >
        {children}
      </blockquote>
    );
  },

  // 水平线
  hr() {
    return (
      <hr
        style={{
          border: 'none',
          borderTop: '1px solid rgba(255, 255, 255, 0.1)',
          margin: '16px 0',
        }}
      />
    );
  },

  // 粗体
  strong({ children }) {
    return (
      <strong style={{ fontWeight: 600, color: '#fff' }}>
        {children}
      </strong>
    );
  },

  // 斜体
  em({ children }) {
    return (
      <em style={{ fontStyle: 'italic' }}>
        {children}
      </em>
    );
  },
};

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return (
    <div className="markdown-content" style={{ color: 'rgba(255, 255, 255, 0.9)' }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}

export default MarkdownRenderer;
