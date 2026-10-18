import path from "node:path";

import { defineConfig } from "@playwright/test";

const isCI = Boolean(process.env.CI);
const frontendPort = Number(process.env.E2E_FRONTEND_PORT ?? 13_000);
const backendPort = Number(process.env.E2E_BACKEND_PORT ?? 18_000);
const frontendURL = `http://127.0.0.1:${frontendPort}`;
const backendURL = `http://127.0.0.1:${backendPort}`;
const backendApiURL = process.env.NEXT_PUBLIC_API_URL ?? `${backendURL}/api`;
const useManagedWebServer = process.env.E2E_SKIP_WEBSERVER !== "1";
const e2eDatabaseURL = `sqlite+aiosqlite:///${path.resolve(__dirname, "viescanner-e2e.db").replaceAll("\\", "/")}`;

const managedWebServer = [
  {
    command:
      `..\\backend\\venv\\Scripts\\python.exe -m uvicorn main:app --host 127.0.0.1 --port ${backendPort}`,
    cwd: "../backend",
    url: `${backendURL}/health`,
    reuseExistingServer: false,
    timeout: 180_000,
    env: {
      OCR_ENGINE: "mock",
      AUTH_REQUIRED: "false",
      DATABASE_URL: e2eDatabaseURL,
      CORS_ORIGINS_RAW: `${frontendURL},http://localhost:${frontendPort}`,
      OCR_RESULT_CACHE_ENABLED: "false",
    },
  },
  {
    command: "node .next/standalone/server.js",
    cwd: ".",
    url: frontendURL,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      PORT: String(frontendPort),
      HOSTNAME: "127.0.0.1",
      NEXT_PUBLIC_API_URL: backendApiURL,
    },
  },
];

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
    baseURL: frontendURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    headless: true,
    permissions: ["camera"],
    launchOptions: {
      args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
    },
  },
  ...(useManagedWebServer ? { webServer: managedWebServer } : {}),
});
