// Playwright E2E config. Specs run against an ALREADY-RUNNING stack (e.g.
// `docker compose up`); this config never starts or stops servers.
//
//   E2E_BASE_URL            stack origin (default http://localhost:8080, the proxy)
//   ADMIN_EMAIL/ADMIN_PASSWORD
//                           bootstrap admin of org A; enables user seeding in
//                           e2e/global-setup.ts. Without them, logged-in specs skip.
//   E2E_ORG_B_ADMIN_EMAIL/E2E_ORG_B_ADMIN_PASSWORD
//                           optional admin of a second org (see e2e/README.md)
//
// No credentials live in the repo. Storage states (session cookies) are
// written to e2e/.auth/, which is git- and docker-ignored.
// Browsers are installed explicitly: `npx playwright install chromium`.
import { defineConfig, devices } from '@playwright/test'

const CI = !!process.env.CI

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.ts',
  globalSetup: './e2e/global-setup.ts',
  outputDir: './test-results',
  fullyParallel: true,
  forbidOnly: CI,
  retries: CI ? 1 : 0,
  // Login is rate limited (5/min per IP): keep parallelism modest.
  workers: CI ? 2 : 4,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: CI ? [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]] : [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:8080',
    ignoreHTTPSErrors: process.env.E2E_IGNORE_HTTPS_ERRORS === '1',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
