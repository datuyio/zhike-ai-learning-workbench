import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  // 子路径基地址：构建时通过 .env.production 的 VITE_BASE_PATH 注入（如 /zhike/），默认 /
  const env = loadEnv(mode, process.cwd(), '');
  const basePath = env.VITE_BASE_PATH || '/';

  return {
    base: basePath,
    plugins: [react()],
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            react: ['react', 'react-dom', 'react-router-dom'],
            query: ['@tanstack/react-query', 'zustand'],
            canvas: ['@xyflow/react', 'framer-motion'],
            markdown: ['react-markdown', 'remark-gfm', 'katex'],
            pdf: ['pdfjs-dist'],
          },
        },
      },
    },
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': 'http://localhost:8001',
        '/health': 'http://localhost:8001',
        '/ws': {
          target: 'ws://localhost:8001',
          ws: true,
        },
      },
    },
  };
});
