import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import path from 'path';

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: path.resolve(__dirname, '../server/dist'),
    emptyOutDir: true,
    assetsDir: 'assets',
    sourcemap: false,
    chunkSizeWarningLimit: 1200,
  },
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:8400',
      '/ws': {
        target: 'ws://localhost:8400',
        ws: true,
      },
    },
  },
});
