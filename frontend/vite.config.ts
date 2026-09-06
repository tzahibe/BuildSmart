import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// Test config (`test: {...}`) lives in the separate vitest.config.ts, not here — the root `vite`
// dependency and vitest's own bundled `vite` are different major versions (rolldown-based vs
// rollup-based), so `@vitejs/plugin-react`'s Plugin type (built against the root `vite`) doesn't
// structurally match `vitest/config`'s `defineConfig` (built against its own nested `vite`) when both
// live in one file's `defineConfig` call. See vitest.config.ts's comment for the other half of this.
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
