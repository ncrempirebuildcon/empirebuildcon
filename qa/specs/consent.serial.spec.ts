/**
 * Consent banner launch state and guards (Phase 6 Task 6.1, Scope 3).
 *
 * Implements:
 * - With today's API (tracking: null), the launch state is guarded:
 *   - / has no "Cookie choices" region and no "Cookie settings" button.
 *   - /projects has no "Cookie choices" region and no "Cookie settings" button.
 *   - A project detail page has no "Cookie choices" region and no "Cookie settings" button.
 * - Re-verified without extra sign-ins (uses CMS_STATE if needed, or public visitor).
 *
 * WHY serial: the launch state is "no tracking IDs", a site-wide setting that settings.spec
 * (an ID saves) and consent-tags.serial.spec change. Running after the "chromium" project, it
 * first restores that state, so it can't race them or inherit an earlier run's IDs.
 */
import { expect, test } from "@playwright/test";
import { apiCall, CMS_STATE } from "../lib/auth";
import { catalogueProject } from "../lib/catalogue";

test.use({ storageState: CMS_STATE });

const NO_IDS = { ga4_id: "", gtm_id: "", google_ads_id: "", meta_pixel_id: "" };

test.beforeAll(async ({ browser }) => {
  const admin = await (await browser.newContext({ storageState: CMS_STATE })).newPage();
  await admin.goto("/admin");
  const res = await apiCall(admin, "PATCH", "/api/v1/admin/settings/tracking", NO_IDS);
  expect(res.status()).toBe(200);
  // The change reaches the cached pages within seconds (D-054).
  await expect
    .poll(
      async () => {
        await admin.goto("/");
        return admin.getByRole("region", { name: "Cookie choices" }).count();
      },
      { intervals: [500, 1000, 2000], timeout: 20_000 },
    )
    .toBe(0);
});

test.describe("Consent Banner launch guard (Task 6.1)", () => {
  test("with today's API, the consent banner and cookie settings button remain hidden on public pages", async ({
    page,
  }) => {
    // 1. Home page (/)
    const homeRes = await page.goto("/");
    expect(homeRes?.status()).toBe(200);

    await expect(page.getByRole("region", { name: "Cookie choices" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Cookie settings" })).toHaveCount(0);

    // 2. Projects list (/projects)
    const projectsRes = await page.goto("/projects");
    expect(projectsRes?.status()).toBe(200);

    await expect(page.getByRole("region", { name: "Cookie choices" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Cookie settings" })).toHaveCount(0);

    // 3. Project detail page
    const project = await catalogueProject(page);
    const detailRes = await page.goto(`/projects/${project.slug}`);
    expect(detailRes?.status()).toBe(200);

    await expect(page.getByRole("region", { name: "Cookie choices" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Cookie settings" })).toHaveCount(0);
  });
});
