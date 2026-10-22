// CMS sign-in journey: sign in, see the shell, check the cookie flags, sign out (SECURITY.md §1).
import { readFileSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { AUTH_FILE } from "../global-setup";

const user = JSON.parse(readFileSync(AUTH_FILE, "utf8")) as {
  email: string;
  password: string;
  name: string;
};

test("wrong password shows the generic message", async ({ page }) => {
  await page.goto("/admin/login");
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Password", { exact: true }).fill("not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  // WHY: Next.js renders its own empty role="alert" route announcer, so match ours by its text.
  await expect(
    page.getByRole("alert").filter({ hasText: "Email or password is incorrect." }),
  ).toBeVisible();
});

test("signed-out visitors are sent to the sign-in page", async ({ page }) => {
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/admin\/login$/);
});

test("staff can sign in and sign out", async ({ page, context }) => {
  await page.goto("/admin/login");
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Password", { exact: true }).fill(user.password);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByText(`Signed in as ${user.name}`)).toBeVisible();

  // SECURITY: the session cookie must be HttpOnly, Secure, SameSite=Lax and host-only.
  const cookie = (await context.cookies()).find((c) => c.name === "__Host-empire_session");
  expect(cookie).toBeDefined();
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.secure).toBe(true);
  expect(cookie?.sameSite).toBe("Lax");
  expect(cookie?.path).toBe("/");

  // The signed-in CMS shell meets WCAG 2.1 AA too (no serious or critical axe issues).
  const axe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(
    axe.violations
      .filter((v) => v.impact === "serious" || v.impact === "critical")
      .map((v) => v.id),
  ).toEqual([]);

  // Nothing about the session is kept in browser storage.
  const stored = await page.evaluate(() => localStorage.length + sessionStorage.length);
  expect(stored).toBe(0);

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/admin\/login$/);
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/admin\/login$/);
});
