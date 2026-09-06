import { defineConfig } from 'vitest/config'

// Separate from vite.config.ts on purpose — see that file's comment. No React plugin needed here:
// Vite's built-in esbuild transform already handles `.tsx` JSX using tsconfig's `jsx: "react-jsx"`
// (automatic runtime), which is all `@testing-library/react` rendering needs; the plugin's extra
// behavior (Fast Refresh) is dev-server-only and irrelevant under Vitest.
export default defineConfig({
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
  },
})
