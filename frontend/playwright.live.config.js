import { defineConfig } from '@playwright/test'

if (!process.env.LIVE_E2E_ORIGIN) throw new Error('Set LIVE_E2E_ORIGIN to the dedicated acceptance service')
if (!process.env.LIVE_E2E_CONTROL_CONTAINER) throw new Error('Set LIVE_E2E_CONTROL_CONTAINER to the acceptance backend container')
export default defineConfig({
  testDir: './tests/live',
  workers: 1,
  retries: 0,
  outputDir: './test-results/live',
  timeout: 360000,
  use: { baseURL: process.env.LIVE_E2E_ORIGIN, headless: true, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
})
