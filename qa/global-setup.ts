/**
 * Runs once before the browser journeys:
 *   1. Brings the database schema up to date (Alembic).
 *   2. Loads the default settings, flags and amenity catalogue, plus the clearly marked sample
 *      projects, sample leads and site visits (`empire-api seed --sample`, dev/test only, D-015).
 *      Safe to run again: repeated runs on the same database add nothing twice.
 *   3. Creates two throwaway accounts with random emails and passwords through the API's
 *      dev/test-only CLI (`empire-api create-user`, refused in staging/production): a super-admin
 *      for the CMS journeys and a sales user for the "sales see only their own leads" journey.
 *   4. Saves the credentials to qa/.auth/e2e-user.json and qa/.auth/e2e-sales.json (git-ignored).
 *
 * SECURITY: the passwords are random per run and only ever exist on this machine or CI runner.
 */
import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { apiEnv } from "./lib/env";

const here = dirname(fileURLToPath(import.meta.url));
export const AUTH_FILE = resolve(here, ".auth/e2e-user.json");
/** The throwaway sales user (role `sales`: leads.read without leads.read_all). */
export const SALES_AUTH_FILE = resolve(here, ".auth/e2e-sales.json");

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
  uv(["empire-api", "seed", "--sample"]);

  const createUser = (file: string, role: string, name: string) => {
    // WHY: example.com is reserved for documentation (RFC 2606) and never receives mail; ".test"
    // addresses are rejected by the API's email validation as a special-use domain.
    const email = `e2e-${role}-${Date.now()}-${randomBytes(3).toString("hex")}@example.com`;
    const password = randomBytes(18).toString("base64url");
    uv(
      [
        "empire-api",
        "create-user",
        "--email",
        email,
        "--name",
        name,
        "--role",
        role,
        "--password-stdin",
      ],
      `${password}\n`,
    );
    writeFileSync(file, JSON.stringify({ email, password, name }), { mode: 0o600 });
  };

  mkdirSync(dirname(AUTH_FILE), { recursive: true });
  createUser(AUTH_FILE, "super_admin", "E2E Admin");
  createUser(SALES_AUTH_FILE, "sales", "E2E Sales");
}
