import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // 允许内网访问
    proxy: {
      // CopilotKit API 代理
      '/copilotkit': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        secure: false,
        configure: (proxy, options) => {
          void options;
          proxy.on('error', (err, req, res) => {
            void req;
            void res;
            console.log('proxy error', err);
          });
          proxy.on('proxyReq', (proxyReq, req, res) => {
            void proxyReq;
            void res;
            console.log('Sending Request:', req.method, req.url);
          });
          proxy.on('proxyRes', (proxyRes, req, res) => {
            void res;
            console.log('Received Response:', proxyRes.statusCode, req.url);
          });
        },
      },
      // 原有 API 代理
      '/sessions': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
