// Phone width: no CMS page scrolls sideways at 390 × 844 (DESIGN_SYSTEM §1 "readable at night on
// a phone"). Wide tables scroll inside their own region instead of the page.
import { expect, test, type Page } from "@playwright/test";
import { CMS_STATE } from "../lib/auth";

// Signed in once by auth.setup.ts (the API limits sign-ins per network).
test.use({ storageState: CMS_STATE, viewport: { width: 390, height: 844 } });

async function expectNoSideScroll(page: Page, label: string) {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(
    scrollWidth,
    `${label}: ${scrollWidth}px of content on a ${clientWidth}px screen`,
  ).toBeLessThanOrEqual(clientWidth);
}

test("the projects list fits a phone screen", async ({ page }) => {
  await page.goto("/admin/projects");
  await expect(page.getByRole("table", { name: "Projects" })).toBeVisible();
  await expectNoSideScroll(page, "/admin/projects");
});

test("every tab of the project editor fits a phone screen", async ({ page }) => {
  // The sample project has content on every tab, including the wide configurations table.
  await page.goto("/admin/projects?q=sample-project-a");
  await page.getByRole("link", { name: "Sample — Project A" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Sample — Project A" })).toBeVisible();
  const tabs = await page.getByRole("tab").allTextContents();
  expect(tabs.length).toBeGreaterThan(8);
  for (const name of tabs) {
    await page.getByRole("tab", { name, exact: true }).click();
    await expect(page.getByRole("tabpanel", { name, exact: true })).toBeVisible();
    await expectNoSideScroll(page, `editor tab ${name}`);
  }
});

test("the catalogue fits a phone screen", async ({ page }) => {
  await page.goto("/admin/catalogue");
  await expect(page.getByRole("table", { name: "Cities" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Amenities" })).toBeVisible();
  await expectNoSideScroll(page, "/admin/catalogue");
});
