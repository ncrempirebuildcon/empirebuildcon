/**
 * Consent banner launch state and guards (Phase 6 Task 6.1, Scope 3).
 *
 * Implements:
 * - With today's API (tracking: null), the launch state is guarded:
 *   - / has no "Cookie choices" region and no "Cookie settings" button.
 *   - /projects has no "Cookie choices" region and no "Cookie settings" button.
 *   - A project detail page has no "Cookie choices" region and no "Cookie settings" button.
 * - Re-verified without extra sign-ins (uses CMS_STATE if needed, or public visitor).
 */
import { expect, test } from "@playwright/test";
import { CMS_STATE } from "../lib/auth";
import { catalogueProject } from "../lib/catalogue";

test.use({ storageState: CMS_STATE });

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
