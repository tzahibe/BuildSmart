import { defineConfig } from '@playwright/test'

// Uses the system-installed Google Chrome (channel: 'chrome') rather than a Playwright-managed
// Chromium download — this machine already has Chrome installed and has no other browser binaries
// cached, so this avoids a large network download just to run these E2E checks.
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5183',
    channel: 'chrome',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
})
