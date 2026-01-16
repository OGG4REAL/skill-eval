import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'

// 根据 URL 参数决定使用哪个 App
// ?mode=legacy 使用旧版 App，否则使用新的 CopilotApp
const urlParams = new URLSearchParams(window.location.search);
const mode = urlParams.get('mode');

async function main() {
  let AppComponent;
  
  if (mode === 'legacy') {
    // 旧版 App（保留兼容性）
    const { default: App } = await import('./App.tsx');
    AppComponent = App;
  } else {
    // 新版 CopilotApp（默认）
    const { default: CopilotApp } = await import('./CopilotApp.tsx');
    AppComponent = CopilotApp;
  }
  
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <AppComponent />
    </StrictMode>,
  );
}

main();
