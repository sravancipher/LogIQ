import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const backendTarget = env.VITE_API_BASE || 'http://localhost:8000';
  const isProd = mode === 'production';

  return {
    // In production the React app is served at /app by FastAPI
    base: isProd ? '/app/' : '/',
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
