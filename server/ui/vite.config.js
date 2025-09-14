import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Allow overriding the backend target via env, default to local aiohttp server
const backendTarget = process.env.BACKEND_URL || 'http://localhost:8080';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // API endpoints proxied to the Python backend during dev
      '/api': {
        target: backendTarget,
        changeOrigin: true,
        secure: false,
      },
      // Static assets referenced by the UI (e.g., logos under /static)
      '/static': {
        target: backendTarget,
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
