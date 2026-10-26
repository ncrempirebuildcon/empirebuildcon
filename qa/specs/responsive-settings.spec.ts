// Phone width (390 × 844): no sideways page scroll on the Phase 4 part 5 screens (Users &
// roles, the audit log, My account and every Settings section). Wide tables scroll inside their
// own region instead of the page.
import { expect, test, type Page } from "@playwright/test";
import { CMS_STATE } from "../lib/auth";

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

test("users, the audit log and My account fit a phone screen", async ({ page }) => {
  await page.goto("/admin/users");
  await expect(page.getByRole("table", { name: "Staff accounts" })).toBeVisible();
  await expectNoSideScroll(page, "/admin/users");
  await page.getByRole("button", { name: "+ Invite user" }).click();
  await expect(page.getByRole("form", { name: "Invite a user" })).toBeVisible();
  await expectNoSideScroll(page, "invite form");
  await page
    .getByRole("button", { name: /^Manage/ })
    .first()
    .click();
  await expect(page.getByRole("list", { name: /^Actions for/ })).toBeVisible();
  await expectNoSideScroll(page, "user panel");

  await page.goto("/admin/audit");
  await expect(page.getByRole("region", { name: "Audit entries table" })).toBeVisible();
  await expectNoSideScroll(page, "/admin/audit");

  await page.goto("/admin/account");
  await expect(page.getByRole("form", { name: "Change password" })).toBeVisible();
  await expectNoSideScroll(page, "/admin/account");
});

test("every Settings section fits a phone screen", async ({ page }) => {
  await page.goto("/admin/settings");
  const tabs = page.getByRole("tablist", { name: "Settings sections" }).getByRole("tab");
  await expect(tabs.first()).toBeVisible();
  const count = await tabs.count();
  for (let index = 0; index < count; index += 1) {
    const tab = tabs.nth(index);
    await tab.click();
    await expect(tab).toHaveAttribute("aria-selected", "true");
    await page.waitForLoadState("networkidle", { timeout: 3000 }).catch(() => undefined);
    await expectNoSideScroll(page, `Settings: ${(await tab.textContent()) ?? index}`);
  }
});
