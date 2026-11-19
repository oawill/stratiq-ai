import { defineConfig } from "@playwright/test";

// End-to-end tests drive the real app (Next.js + FastAPI + Postgres) as a user would.
// Prerequisites: `npm run build`, a migrated DATABASE_URL in .env.local, and a seeded dataset (`python -m stratiq.seed`).
// Test accounts are named e2e-*@stratiq.test and are removed by e2e/teardown.mjs.
// Set E2E_BASE_URL to run the same suite against a deployed site (no local servers are started).
const remote = process.env.E2E_BASE_URL;
const py = process.env.E2E_PYTHON ?? (process.platform === "win32" ? ".venv\\Scripts\\python" : ".venv/bin/python");

export default defineConfig({
  testDir: "e2e",
  timeout: 240_000,
  expect: { timeout: 30_000 },
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  globalTeardown: "./e2e/teardown.mjs",
  use: { baseURL: remote ?? "http://localhost:3101", trace: "retain-on-failure" },
  webServer: remote ? undefined : [
    {
      command: `${py} -W ignore -m uvicorn stratiq.api:app --port 8001`,
      url: "http://127.0.0.1:8001/api/v1/health",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: "npx next start -p 3101",
      url: "http://localhost:3101/login",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: { PY_API_URL: "http://127.0.0.1:8001" },
    },
  ],
});
