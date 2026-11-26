import { defineConfig } from '@playwright/test'

// Smoke tests against a running bench site: BASE_URL defaults to the bench dev server.
export default defineConfig({
  testDir: '.',
  timeout: 30_000,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: process.env.BASE_URL || 'http://127.0.0.1:8000',
    trace: 'off',
    launchOptions: { executablePath: process.env.PW_CHROMIUM || undefined },
  },
})
