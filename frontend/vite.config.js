import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:9990',
      '/ws': { target: 'ws://localhost:9990', ws: true },
    },
  },
  build: { outDir: 'dist' },
})
