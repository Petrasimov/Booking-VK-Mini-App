import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
  ],
  server: {
    host: 'localhost',
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    hmr: {
      protocol: 'ws',
      host: 'localhost',
      port: 5173,
    },
    headers: {
      // Отключает страницу-предупреждение ngrok — иначе VK iframe видит ngrok,
      // а не наше приложение, и VK Bridge не может инициализироваться
      'ngrok-skip-browser-warning': 'true',
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  base: '/', // Базовый путь для VK Mini App
})
