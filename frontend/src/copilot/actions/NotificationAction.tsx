/**
 * 通知渲染 Action
 * 
 * 显示临时通知消息
 */
import { useEffect, useState } from 'react';
import { Info, CheckCircle, AlertTriangle, XCircle, X } from 'lucide-react';
import type { ShowNotificationArgs } from '../types';

interface NotificationActionProps {
  args: ShowNotificationArgs;
}

const NOTIFICATION_STYLES = {
  info: {
    background: 'rgba(59, 130, 246, 0.15)',
    border: '1px solid rgba(59, 130, 246, 0.3)',
    iconColor: '#3B82F6',
    Icon: Info,
  },
  success: {
    background: 'rgba(34, 197, 94, 0.15)',
    border: '1px solid rgba(34, 197, 94, 0.3)',
    iconColor: '#22C55E',
    Icon: CheckCircle,
  },
  warning: {
    background: 'rgba(234, 179, 8, 0.15)',
    border: '1px solid rgba(234, 179, 8, 0.3)',
    iconColor: '#EAB308',
    Icon: AlertTriangle,
  },
  error: {
    background: 'rgba(239, 68, 68, 0.15)',
    border: '1px solid rgba(239, 68, 68, 0.3)',
    iconColor: '#EF4444',
    Icon: XCircle,
  },
};

export function NotificationAction({ args }: NotificationActionProps) {
  const { message, type = 'info', duration = 5000 } = args;
  const [visible, setVisible] = useState(true);
  
  const style = NOTIFICATION_STYLES[type];
  const Icon = style.Icon;

  useEffect(() => {
    if (duration > 0) {
      const timer = setTimeout(() => {
        setVisible(false);
      }, duration);
      return () => clearTimeout(timer);
    }
  }, [duration]);

  if (!visible) return null;

  return (
    <div
      className="notification-action"
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '12px',
        padding: '14px 16px',
        borderRadius: '12px',
        background: style.background,
        border: style.border,
        margin: '8px 0',
        animation: 'fadeIn 0.3s ease',
      }}
    >
      <Icon size={20} color={style.iconColor} style={{ flexShrink: 0, marginTop: '2px' }} />
      <span style={{ flex: 1, color: '#fff', fontSize: '14px', lineHeight: 1.5 }}>
        {message}
      </span>
      <button
        onClick={() => setVisible(false)}
        style={{
          background: 'transparent',
          border: 'none',
          padding: '4px',
          cursor: 'pointer',
          color: 'rgba(255, 255, 255, 0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <X size={16} />
      </button>
    </div>
  );
}

export default NotificationAction;
