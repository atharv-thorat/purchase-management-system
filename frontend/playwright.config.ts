import path from "node:path";

import { defineConfig } from "@playwright/test";

// The E2E run is isolated from the demo: its own SQLite file, backend on :8011, frontend on
// :3011 (own build folder), so it can run while ./dev.sh is serving the demo on :8000/:3000.
const BACKEND_PORT = 8011;
const FRONTEND_PORT = 3011;
const E2E_DB = path.resolve(__dirname, "../backend/e2e.db");

export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { open: "never", outputFolder: "e2e-report" }]],
  outputDir: "e2e-results",
  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    viewport: { width: 1440, height: 900 }, // a laptop screen, as in the live demo
    // Uses the installed Google Chrome. Without Chrome: `npx playwright install chromium`
    // and run with E2E_BUNDLED_CHROMIUM=1.
    channel: process.env.E2E_BUNDLED_CHROMIUM ? undefined : "chrome",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: "bash ../backend/run.sh --reset",
      url: `http://localhost:${BACKEND_PORT}/api/health`,
      env: {
        PORT: String(BACKEND_PORT),
        PMS_DATABASE_URL: `sqlite:///${E2E_DB}`,
        PMS_CORS_ORIGINS: JSON.stringify([`http://localhost:${FRONTEND_PORT}`]),
      },
      reuseExistingServer: false,
      timeout: 240_000,
    },
    {
      command: `npx next dev -p ${FRONTEND_PORT}`,
      url: `http://localhost:${FRONTEND_PORT}/login`,
      env: {
        NEXT_PUBLIC_API_URL: `http://localhost:${BACKEND_PORT}/api`,
        NEXT_DIST_DIR: ".next-e2e",
        NEXT_TELEMETRY_DISABLED: "1",
      },
      reuseExistingServer: false,
      timeout: 240_000,
    },
  ],
});

export const E2E_API = `http://localhost:${BACKEND_PORT}`;
