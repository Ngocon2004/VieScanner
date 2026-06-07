import { defineConfig } from "@playwright/test";

const isCI = Boolean(process.env.CI);

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: {
    timeout: 15_000,
  },
  workers: 1,
  retries: isCI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    headless: true,
  },
  webServer: [
    {
      command:
        "..\\backend\\venv\\Scripts\\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000",
      cwd: "../backend",
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: !isCI,
      timeout: 180_000,
      gracefulShutdown: {
        signal: "SIGINT",
        timeout: 5_000,
      },
      env: {
        OCR_ENGINE: "mock",
        AUTH_REQUIRED: "false",
        DATABASE_URL: "sqlite+aiosqlite:///D:/Nam4/Web_New/VieScanner/frontend/viescanner-e2e.db",
        CORS_ORIGINS_RAW: "http://127.0.0.1:3000,http://localhost:3000",
        OCR_RESULT_CACHE_ENABLED: "false",
      },
    },
    {
      command: "node .next/standalone/server.js",
      cwd: ".",
      url: "http://127.0.0.1:3000",
      reuseExistingServer: !isCI,
      timeout: 120_000,
      gracefulShutdown: {
        signal: "SIGINT",
        timeout: 5_000,
      },
      env: {
        PORT: "3000",
        HOSTNAME: "127.0.0.1",
        NEXT_PUBLIC_API_URL: "http://127.0.0.1:8000/api",
      },
    },
  ],
});
