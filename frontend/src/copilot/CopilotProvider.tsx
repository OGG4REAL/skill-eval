/**
 * CopilotKit Provider 包装组件
 * 
 * 提供 CopilotKit 上下文，使子组件能够使用 CopilotKit hooks
 */
import { CopilotKit } from '@copilotkit/react-core';
import type { ReactNode } from 'react';

interface CopilotProviderProps {
  children: ReactNode;
}

export function CopilotProvider({ children }: CopilotProviderProps) {
  return (
    <CopilotKit
      runtimeUrl="/copilotkit/chat"
      showDevConsole={import.meta.env.DEV}
    >
      {children}
    </CopilotKit>
  );
}
