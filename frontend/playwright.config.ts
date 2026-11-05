import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:5173",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
  },
  webServer: process.env.E2E_EXTERNAL
    ? undefined
    : [
        {
          command:
            "../.venv/bin/uvicorn backend.app.main:app --app-dir .. --host 127.0.0.1 --port 8000",
          url: "http://127.0.0.1:8000/health",
          reuseExistingServer: false,
          timeout: 60_000,
          env: {
            DATABASE_URL: "sqlite:///../storage/e2e.db",
            STORAGE_DIR: "../storage/e2e-datasets",
          },
        },
        {
          command: "npm run dev -- --port 5173",
          url: "http://127.0.0.1:5173",
          reuseExistingServer: false,
        },
      ],
});
