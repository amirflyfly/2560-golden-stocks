import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8765';
const pythonExecutable = process.env.PYTHON || process.env.PYTHON_EXECUTABLE || 'python';
const backendCommand = process.env.E2E_BACKEND_COMMAND || `${pythonExecutable} ../scripts/run_e2e_backend.py`;

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  webServer: {
    command: backendCommand,
    url: `${baseURL}/health`,
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
    cwd: '.',
    env: {
      APP_ENV: 'development',
      APP_DEBUG: '0',
      MARKET_DATA_PROVIDER: 'mock',
      ALLOW_MOCK_MARKET_DATA: '1',
      SECRET_KEY: 'e2e-dev-secret-key-please-do-not-use-in-prod',
    },
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH
          ? { channel: undefined, launchOptions: { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH } }
          : {}),
      },
    },
  ],
});
