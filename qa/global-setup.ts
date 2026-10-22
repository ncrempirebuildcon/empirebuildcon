/**
 * Runs once before the browser journeys:
 *   1. Brings the database schema up to date (Alembic).
 *   2. Creates a throwaway super-admin with a random email and password through the API's
 *      dev/test-only CLI (`empire-api create-user`, refused in staging/production).
 *   3. Saves the credentials to qa/.auth/e2e-user.json (git-ignored) for login.spec.ts.
 *
 * SECURITY: the password is random per run and only ever exists on this machine or CI runner.
 */
import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { apiEnv } from "./lib/env";

const here = dirname(fileURLToPath(import.meta.url));
export const AUTH_FILE = resolve(here, ".auth/e2e-user.json");

export default function globalSetup() {
  const env = { ...process.env, ...apiEnv() };
  const apiDir = resolve(here, "../apps/api");
  const uv = (args: string[], input?: string) =>
    execFileSync("uv", ["--directory", apiDir, "run", ...args], {
      env,
      input,
      stdio: [input === undefined ? "ignore" : "pipe", "inherit", "inherit"],
    });

  uv(["alembic", "upgrade", "head"]);

  // WHY: example.com is reserved for documentation (RFC 2606) and never receives mail; ".test"
  // addresses are rejected by the API's email validation as a special-use domain.
  const email = `e2e-${Date.now()}-${randomBytes(3).toString("hex")}@example.com`;
  const password = randomBytes(18).toString("base64url");
  uv(
    [
      "empire-api",
      "create-user",
      "--email",
      email,
      "--name",
      "E2E Admin",
      "--role",
      "super_admin",
      "--password-stdin",
    ],
    `${password}\n`,
  );

  mkdirSync(dirname(AUTH_FILE), { recursive: true });
  writeFileSync(AUTH_FILE, JSON.stringify({ email, password, name: "E2E Admin" }), { mode: 0o600 });
}
