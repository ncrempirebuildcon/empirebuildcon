/**
 * Playwright: browser journeys and accessibility checks (handbook/ARCHITECTURE.md §21).
 *
 * How it works:
 *   1. `webServer` starts the API (uvicorn) and the built web app (`next start`) unless they are
 *      already running locally. Build the web app first: `pnpm --filter @empire/web build`.
 *   2. global-setup.ts migrates the database and creates a throwaway super-admin.
 *   3. The "setup" project (specs/auth.setup.ts) signs that user in once and saves the session for
 *      the CMS journeys (lib/auth.ts `CMS_STATE`).
 *   4. Specs run in Chromium only (the browser most visitors use in India; others come in Phase 8).
 *
 * WHY sign in once: the API allows 10 sign-in attempts per network per 15 minutes
 * (handbook/SECURITY.md §1). One sign-in per CMS test would trip that limit, as it should.
 *
 * WHY: PW_CHROMIUM_PATH lets a machine use a pre-installed Chromium (e.g. Claude's workspace);
 * CI installs the browser that matches @playwright/test instead.
 */
import { existsSync } from "node:fs";
import { defineConfig, devices } from "@playwright/test";
import { API_URL, WEB_URL, apiEnv } from "./lib/env";

const env = apiEnv();
// WHY: On Windows developer machines without playwright-installed headless-shell, fallback to installed Chrome.
// CI and Linux environments use PW_CHROMIUM_PATH or Playwright-managed Chromium.
const defaultChrome =
  process.platform === "win32" &&
  existsSync("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")
    ? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    : undefined;
const executablePath = process.env.PW_CHROMIUM_PATH || defaultChrome;

export default defineConfig({
  testDir: "./specs",
  globalSetup: "./global-setup.ts",
  fullyParallel: true,
  // WHY workers: 2: Matches CI (2 vCPUs) and avoids Windows socket exhaustion (ECONNRESET -4077)
  // on a single-process uvicorn server when > 2 parallel browser contexts hammer loopback HTTP.
  workers: process.env.CI ? 2 : 2,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // WHY 60 s per test (default 30 s): the axe journeys walk every tab or section of a CMS screen,
  // and on a 2-CPU machine running two workers they passed 30 s with nothing failing (3 Nov 2026,
  // project editor, Settings, offers). Only the time limit changes; `expect` waits stay at 5 s
  // unless a test says why it needs longer.
  timeout: 60_000,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: WEB_URL,
    trace: "retain-on-failure",
    ...(executablePath ? { launchOptions: { executablePath } } : {}),
  },
  projects: [
    { name: "setup", testMatch: /.*\.setup\.ts/, use: { ...devices["Desktop Chrome"] } },
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
      dependencies: ["setup"],
      testIgnore: [/\.serial\.spec\.ts$/, /\.lighthouse\.spec\.ts$/],
    },
    // WHY a separate project: these specs need the outbox to themselves (no other spec draining
    // it), so they run after "chromium" has finished (task 5.3).
    {
      name: "serial",
      use: { ...devices["Desktop Chrome"] },
      dependencies: ["chromium"],
      testMatch: /\.serial\.spec\.ts$/,
      // One at a time, so two serial specs never drain the outbox under each other.
      workers: 1,
    },
    // Lighthouse budgets (task 5.7, D-049): run on their own (`pnpm --filter @empire/qa
    // lighthouse`, CI job "lighthouse"), because scores need a quiet machine, not one running the
    // whole suite. `pnpm e2e` names its projects, so it never runs this one.
    {
      name: "lighthouse",
      dependencies: ["setup"],
      testMatch: /\.lighthouse\.spec\.ts$/,
      workers: 1,
      // A missed budget is a result to look at, not a flake to retry (D-049).
      retries: 0,
    },
  ],
  webServer: [
    {
      command: "uv --directory ../apps/api run uvicorn empire_api.main:app --port 8000",
      url: `${API_URL}/api/health/live`,
      env: {
        ...env,
        WEB_REVALIDATE_URL: `${WEB_URL}/_internal/revalidate`,
        REVALIDATE_SECRET: env.REVALIDATE_SECRET ?? "test-revalidate-secret-minimum-32-chars-long",
      },
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: "pnpm --filter @empire/web start",
      url: WEB_URL,
      env: {
        API_ORIGIN: API_URL,
        SITE_URL: WEB_URL,
        EDGE_PROXY_KEY: env.EDGE_PROXY_KEY ?? "",
        CSP_ENFORCE: "true",
        // CMS redirects reach the website within a second here (lib/public/redirects.ts).
        REDIRECT_CACHE_SECONDS: "1",
        REVALIDATE_SECRET: env.REVALIDATE_SECRET ?? "test-revalidate-secret-minimum-32-chars-long",
      },
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
