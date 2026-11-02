/**
 * Environment for the browser journeys: where the web app and API run, and the API's settings.
 *
 * SECURITY: API secrets for the test run are generated fresh on each run (unless CI provides them),
 * so no real secret is ever needed or stored for testing. They are written into process.env once,
 * so the API server, global setup and Playwright workers all see the same values.
 */
import { randomBytes } from "node:crypto";

export const WEB_URL = process.env.E2E_WEB_URL ?? "http://localhost:3000";
export const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";

const generated = (bytes: number) => randomBytes(bytes).toString("base64url");

const defaults: Record<string, () => string> = {
  APP_ENV: () => "test",
  DATABASE_URL: () => "postgresql+psycopg://empire:empire@localhost:5432/empire_dev",
  SITE_URL: () => WEB_URL,
  SESSION_SECRET: () => generated(48),
  // A Fernet key is 32 random bytes in url-safe base64 with padding.
  DATA_ENCRYPTION_KEY: () => `${generated(32)}=`,
  INTERNAL_API_KEY: () => generated(48),
  IP_HASH_SALT: () => generated(48),
  // The web proxy and the API share this key, exactly as in production (apps/web/src/proxy.ts).
  EDGE_PROXY_KEY: () => generated(48),
  REVALIDATE_SECRET: () => "test-revalidate-secret-minimum-32-chars-long",
  WEB_REVALIDATE_URL: () => `${WEB_URL}/_internal/revalidate`,
  // WHY explicit: the media journeys must never reach Cloudinary. The fake store keeps files on
  // disk and offers a Cloudinary-shaped upload endpoint, so the browser flow runs unchanged
  // (apps/api README "Media store"). The API's default in test is fake as well.
  MEDIA_STORE: () => "fake",
};

/** Settings for the API process and its CLI; fills any missing value once per test run. */
export function apiEnv(): Record<string, string> {
  const env: Record<string, string> = {};
  for (const [name, make] of Object.entries(defaults)) {
    process.env[name] ??= make();
    env[name] = process.env[name] as string;
  }
  return env;
}
