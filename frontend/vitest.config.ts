import { defineConfig } from 'vitest/config'

// Separate from vite.config.ts on purpose — see that file's comment. No React plugin needed here:
// Vite's built-in esbuild transform already handles `.tsx` JSX using tsconfig's `jsx: "react-jsx"`
// (automatic runtime), which is all `@testing-library/react` rendering needs; the plugin's extra
// behavior (Fast Refresh) is dev-server-only and irrelevant under Vitest.
export default defineConfig({
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
    // Scoped to unit tests under src/ only — Playwright's own spec files live under e2e/ and use a
    // different test runner (`@playwright/test`'s `test`/`describe`), which conflicts if Vitest's
    // default `*.spec.ts` glob also picks them up.
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
