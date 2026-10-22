// Smoke: the site answers, the 404 page works, and /api/* reaches the API without redirects.
import { expect, test } from "@playwright/test";

test("home page loads with the holding message", async ({ page }) => {
  const response = await page.goto("/");
  expect(response?.status()).toBe(200);
  await expect(page).toHaveTitle(/Empire/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Our new website is on its way");
});

test("unknown pages show the 404 page", async ({ page }) => {
  const response = await page.goto("/this-page-does-not-exist");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("moved or doesn");
});

test("security headers are set on pages", async ({ request }) => {
  const response = await request.get("/");
  const headers = response.headers();
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["x-powered-by"]).toBeUndefined();
});

test("/api/* is proxied to the API", async ({ request }) => {
  const response = await request.get("/api/health/live");
  expect(response.status()).toBe(200);
  expect(await response.json()).toMatchObject({ status: "ok" });
});

// DO NOT CHANGE: a trailing slash must never cause a redirect (ARCHITECTURE.md §3, Current Investor bug).
test("API paths with a trailing slash are not redirected", async ({ request }) => {
  const response = await request.get("/api/health/live/", { maxRedirects: 0 });
  expect(response.status()).toBe(200);
});
