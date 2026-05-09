import { defineConfig, devices } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const baseURL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8765';
const rootDir = path.resolve('..');

function firstExistingPath(candidates) {
  return candidates.find((candidate) => candidate && fs.existsSync(candidate));
}

function resolvePythonExecutable() {
  if (process.env.PYTHON_EXECUTABLE) return process.env.PYTHON_EXECUTABLE;
  if (process.env.PYTHON) return process.env.PYTHON;
  return firstExistingPath([
    path.join(rootDir, '.venv-codex', 'Scripts', 'python.exe'),
    path.join(rootDir, '.venv', 'Scripts', 'python.exe'),
    path.join(rootDir, '.venv-codex', 'bin', 'python'),
    path.join(rootDir, '.venv', 'bin', 'python'),
  ]) || 'python';
}

function resolveChromiumExecutable() {
  if (process.env.PLAYWRIGHT_EXECUTABLE_PATH) return process.env.PLAYWRIGHT_EXECUTABLE_PATH;
  return firstExistingPath([
    'D:\\playwright-browsers\\chromium-1208\\chrome-win64\\chrome.exe',
    'D:\\playwright-browsers\\chromium-1217\\chrome-win64\\chrome.exe',
  ]);
}

const pythonExecutable = resolvePythonExecutable();
const chromiumExecutable = resolveChromiumExecutable();
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
      MARKET_DATA_PROVIDER: 'mootdx',
      MARKET_DATA_FALLBACKS: 'akshare',
      SECRET_KEY: 'e2e-dev-secret-key-please-do-not-use-in-prod',
    },
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        ...(chromiumExecutable
          ? { channel: undefined, launchOptions: { executablePath: chromiumExecutable } }
          : {}),
      },
    },
  ],
});
