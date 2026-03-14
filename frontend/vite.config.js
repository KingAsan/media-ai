import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/recommend': 'http://127.0.0.1:8000',
      '/register': 'http://127.0.0.1:8000',
      '/token': 'http://127.0.0.1:8000',
      '/download': 'http://127.0.0.1:8000',
      '/manifest.json': 'http://127.0.0.1:8000',
      '/icon.png': 'http://127.0.0.1:8000',
      '/service-worker.js': 'http://127.0.0.1:8000',
      '/sakura.gif': 'http://127.0.0.1:8000'
    }
  }
});
