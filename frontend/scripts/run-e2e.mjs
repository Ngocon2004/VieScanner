import { spawn, spawnSync } from "node:child_process";
import process from "node:process";
import { fileURLToPath } from "node:url";

const frontendPort = Number(process.env.E2E_FRONTEND_PORT ?? 13_000);
const backendPort = Number(process.env.E2E_BACKEND_PORT ?? 18_000);
const frontendURL = `http://127.0.0.1:${frontendPort}`;
const backendURL = `http://127.0.0.1:${backendPort}`;
const backendApiURL = process.env.NEXT_PUBLIC_API_URL ?? `${backendURL}/api`;
const isWindows = process.platform === "win32";

const children = [];
let shuttingDown = false;

function spawnManaged(command, args, options = {}) {
  const env = { ...process.env };
  for (const [key, value] of Object.entries(options.env ?? {})) {
    if (value !== undefined) env[key] = value;
  }

  const child = spawn(command, args, {
    cwd: options.cwd ?? process.cwd(),
    env,
    stdio: "inherit",
    windowsHide: true,
  });
  children.push(child);
  child.on("exit", (code, signal) => {
    if (!shuttingDown && code !== 0 && code !== null) {
      console.error(`${command} exited with code ${code}${signal ? ` (${signal})` : ""}`);
    }
  });
  return child;
}

function waitForExit(child) {
  return new Promise((resolve) => {
    child.on("exit", (code, signal) => {
      resolve(code ?? (signal ? 1 : 0));
    });
  });
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForURL(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let lastError = "";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (response.ok) return;
      lastError = `HTTP ${response.status}`;
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
    }
    await delay(500);
  }
  throw new Error(`Timed out waiting for ${url}${lastError ? ` (${lastError})` : ""}`);
}

function killTree(child) {
  if (!child.pid || child.exitCode !== null) return;
  if (isWindows) {
    spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
      stdio: "ignore",
      windowsHide: true,
    });
    return;
  }
  child.kill("SIGTERM");
}

async function shutdownChildren() {
  shuttingDown = true;
  for (const child of [...children].reverse()) {
    killTree(child);
  }
  await Promise.all(
    children.map((child) =>
      child.exitCode !== null
        ? Promise.resolve()
        : Promise.race([waitForExit(child), delay(5_000)]),
    ),
  );
}

const backendPython = isWindows
  ? "..\\backend\\venv\\Scripts\\python.exe"
  : "../backend/venv/bin/python";
const e2eDatabaseURL = `sqlite+aiosqlite:///${fileURLToPath(new URL("../viescanner-e2e.db", import.meta.url)).replaceAll("\\", "/")}`;

function migrateE2EDatabase() {
  const result = spawnSync(
    backendPython,
    ["-m", "alembic", "-c", "app/db/alembic.ini", "upgrade", "head"],
    {
      cwd: "../backend",
      env: { ...process.env, DATABASE_URL: e2eDatabaseURL },
      stdio: "inherit",
      windowsHide: true,
    },
  );
  if (result.status !== 0) throw new Error("E2E database migration failed");
}

async function main() {
  migrateE2EDatabase();
  spawnManaged(
    backendPython,
    ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", String(backendPort)],
    {
      cwd: "../backend",
      env: {
        OCR_ENGINE: "mock",
        AUTH_REQUIRED: "false",
        DATABASE_URL: e2eDatabaseURL,
        CORS_ORIGINS_RAW: `${frontendURL},http://localhost:${frontendPort}`,
        OCR_RESULT_CACHE_ENABLED: "false",
      },
    },
  );

  spawnManaged("node", [".next/standalone/server.js"], {
    env: {
      PORT: String(frontendPort),
      HOSTNAME: "127.0.0.1",
      NEXT_PUBLIC_API_URL: backendApiURL,
    },
  });

  let code = 1;
  try {
    await Promise.all([
      waitForURL(`${backendURL}/health`, 180_000),
      waitForURL(frontendURL, 120_000),
    ]);

    const playwright = spawnManaged(
      process.execPath,
      ["node_modules/@playwright/test/cli.js", "test", ...process.argv.slice(2)],
      {
        env: {
          E2E_SKIP_WEBSERVER: "1",
          E2E_BACKEND_PORT: String(backendPort),
          E2E_FRONTEND_PORT: String(frontendPort),
          NEXT_PUBLIC_API_URL: backendApiURL,
          DOCS_SCREENSHOT_DIR: process.env.DOCS_SCREENSHOT_DIR,
        },
      },
    );
    code = await waitForExit(playwright);
  } finally {
    await shutdownChildren();
  }
  process.exit(code);
}

main().catch(async (err) => {
  console.error(err);
  await shutdownChildren();
  process.exit(1);
});
