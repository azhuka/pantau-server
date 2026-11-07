import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

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
    chunkSizeWarningLimit: 1500,
  },
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://127.0.0.1:8400',
      '/ws': {
        target: 'ws://127.0.0.1:8400',
        ws: true,
      },
    },
  },
})
