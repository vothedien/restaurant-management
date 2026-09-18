import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Explicit test entry point. The normal Vite config never imports this file.
// Both proxy destinations are fixed to the disposable SQLite API, never .env.
export default defineConfig({
  root: fileURLToPath(new URL('..', import.meta.url)),
  envDir: false,
  cacheDir: fileURLToPath(new URL('../../tmp/inventory-real-auth-vite-cache', import.meta.url)),
  plugins: [react(), {
    name: 'inventory-test-environment-marker',
    configureServer(server) {
      server.middlewares.use('/__test__/auth-adapter', (_request, response) => {
        response.setHeader('Content-Type', 'application/json');
        response.end(JSON.stringify({ adapter: 'inventory-real-backend', apiTarget: 'http://127.0.0.1:8011' }));
      });
    },
  }],
  define: { 'import.meta.env.VITE_API_URL': JSON.stringify('') },
  server: {
    host: '127.0.0.1', port: 5174, strictPort: true,
    proxy: {
      '/api/v1': { target: 'http://127.0.0.1:8011', changeOrigin: true },
      '/__test__': { target: 'http://127.0.0.1:8011', changeOrigin: true },
    },
  },
});
