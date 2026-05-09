import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const backendTarget = process.env.VITE_BACKEND_PROXY || 'http://127.0.0.1:8765';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/api': backendTarget
    }
  },
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    sourcemap: true
  }
});
