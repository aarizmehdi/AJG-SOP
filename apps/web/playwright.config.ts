import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const repositoryRoot = fileURLToPath(new URL('../../', import.meta.url));

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:5173',
    browserName: 'chromium',
    channel: 'chrome',
    headless: true,
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command:
        'uv run uvicorn apps.api.app.main:app --host 127.0.0.1 --port 8000',
      cwd: repositoryRoot,
      url: 'http://127.0.0.1:8000/health',
      env: {
        APP_MODE: 'fixture',
        LLM_PROVIDER: 'fixture',
        WEB_ORIGIN: 'http://127.0.0.1:5173',
      },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command:
        'npm run dev --workspace @ajt/web -- --host 127.0.0.1 --port 5173',
      cwd: repositoryRoot,
      url: 'http://127.0.0.1:5173',
      env: {
        VITE_APP_MODE: 'fixture',
        VITE_API_URL: 'http://127.0.0.1:8000/api/v1',
      },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
