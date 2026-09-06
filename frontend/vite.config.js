import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const backendTarget = env.VITE_API_BASE || 'http://localhost:8000';
  const isProd = mode === 'production';

  return {
    // Two production build targets:
    // - default 'production' mode: bundled into backend/dist and served at /app by FastAPI
    // - 'pages' mode: built standalone for GitHub Pages, served at the domain root
    base: mode === 'pages' ? '/' : isProd ? '/app/' : '/',
    plugins: [react()],
    server: {
      port: 8001,
      proxy: {
        '/api': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/dashboard/assets': {
          target: backendTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
