/**
 * Playwright: browser journeys and accessibility checks (handbook/ARCHITECTURE.md §21).
 *
 * How it works:
 *   1. `webServer` starts the API (uvicorn) and the built web app (`next start`) unless they are
 *      already running locally. Build the web app first: `pnpm --filter @empire/web build`.
 *   2. global-setup.ts migrates the database and creates a throwaway super-admin.
 *   3. Specs run in Chromium only (the browser most visitors use in India; others come in Phase 8).
 *
 * WHY: PW_CHROMIUM_PATH lets a machine use a pre-installed Chromium (e.g. Claude's workspace);
 * CI installs the browser that matches @playwright/test instead.
 */
import { defineConfig, devices } from "@playwright/test";
import { API_URL, WEB_URL, apiEnv } from "./lib/env";

const env = apiEnv();
const executablePath = process.env.PW_CHROMIUM_PATH;

export default defineConfig({
  testDir: "./specs",
  globalSetup: "./global-setup.ts",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: WEB_URL,
    trace: "retain-on-failure",
    ...(executablePath ? { launchOptions: { executablePath } } : {}),
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "uv --directory ../apps/api run uvicorn empire_api.main:app --port 8000",
      url: `${API_URL}/api/health/live`,
      env,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: "pnpm --filter @empire/web start",
      url: WEB_URL,
      env: { API_ORIGIN: API_URL, SITE_URL: WEB_URL, EDGE_PROXY_KEY: env.EDGE_PROXY_KEY ?? "" },
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
