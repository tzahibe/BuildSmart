import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Dev-only proxy to the FastAPI backend (see backend/app/main.py), so the
    // frontend can call same-origin paths like `/projects` without CORS setup.
    proxy: {
      '/projects': 'http://127.0.0.1:8000',
      '/localities': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
})
