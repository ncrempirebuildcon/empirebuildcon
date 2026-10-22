/**
 * Helpers for CMS journeys: sign in as the throwaway super-admin from global-setup.ts, call the
 * API as that user (with the session cookie and CSRF token, exactly like the CMS does), and run axe.
 *
 * CMS specs reuse one signed-in session (`CMS_STATE`, saved by specs/auth.setup.ts) because the API
 * allows only 10 sign-in attempts per network per 15 minutes (SECURITY.md §1).
 *
 * SECURITY: the credentials and the saved session exist only for this test run (qa/.auth is
 * git-ignored); the CSRF token is read from /auth/me like the browser app does, never stored.
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, type APIResponse, type Page } from "@playwright/test";
import { AUTH_FILE } from "../global-setup";

/** Saved browser state (session cookie) of the signed-in throwaway super-admin. */
export const CMS_STATE = resolve(dirname(AUTH_FILE), "cms-state.json");

export interface E2EUser {
  email: string;
  password: string;
  name: string;
}

export function e2eUser(): E2EUser {
  return JSON.parse(readFileSync(AUTH_FILE, "utf8")) as E2EUser;
}

/** Signs in through the real form and waits for the CMS dashboard. */
export async function signIn(page: Page): Promise<void> {
  const user = e2eUser();
  await page.goto("/admin/login");
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Password", { exact: true }).fill(user.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/admin$/);
}

/** A unique suffix so repeated runs against the same database never clash on names or slugs. */
export function runId(): string {
  return `${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`;
}

/** Calls the API through the website as the signed-in user (cookie + X-CSRF-Token). */
export async function apiCall(
  page: Page,
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE",
  path: string,
  data?: unknown,
): Promise<APIResponse> {
  const me = await page.request.get("/api/v1/auth/me");
  expect(me.status()).toBe(200);
  const { csrf_token: csrf } = (await me.json()) as { csrf_token: string };
  return page.request.fetch(path, {
    method,
    data,
    headers: { "X-CSRF-Token": csrf },
  });
}

/** axe (WCAG 2.1 A/AA): the serious and critical violations on the page, as "id: help" lines. */
export async function seriousA11yViolations(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join(", ")})`);
}
