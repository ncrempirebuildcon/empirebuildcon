// Accessibility of the Phase 4 part 5 screens: axe finds no serious or critical WCAG 2.1 A/AA
// issues on Users & roles (invite form open, a user's panel and a confirm dialog), the audit log
// (an entry's details open, the empty state), My account, and every Settings section.
// No new sign-ins: the saved super-admin session is reused.
import { expect, test, type Page } from "@playwright/test";
import { CMS_STATE, seriousA11yViolations } from "../lib/auth";

test.use({ storageState: CMS_STATE });

async function expectClean(page: Page, label: string) {
  await expect(page).toHaveTitle(/\S/);
  expect(await seriousA11yViolations(page), label).toEqual([]);
}

test("Users & roles is accessible with the invite form, a user's panel and a dialog", async ({
  page,
}) => {
  await page.goto("/admin/users");
  await expect(page.getByRole("table", { name: "Staff accounts" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Permissions of each role" })).toBeVisible();
  await expectClean(page, "/admin/users");

  await page.getByRole("button", { name: "+ Invite user" }).click();
  await expect(page.getByRole("form", { name: "Invite a user" })).toBeVisible();
  await page.getByRole("button", { name: "Send invite link" }).click();
  await expect(page.getByText("Enter their work email.")).toBeVisible();
  await expectClean(page, "invite form with errors");
  await page.getByRole("button", { name: "Close" }).first().click();

  // The role picker says what the chosen role is for.
  await page.getByRole("button", { name: /^Marketing/ }).click();
  await expect(page.getByRole("button", { name: /^Marketing/ })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(
    page.getByRole("status").filter({ hasText: "Sees lead counts by source" }),
  ).toBeVisible();

  // Someone else's active account: the panel and a confirmation.
  await page
    .getByRole("table", { name: "Staff accounts" })
    .getByRole("row")
    .filter({ hasText: "Active", hasNot: page.getByText("(you)") })
    .getByRole("button", { name: /^Manage/ })
    .first()
    .click();
  const actions = page.getByRole("list", { name: /^Actions for/ });
  await expect(actions).toBeVisible();
  await expectClean(page, "user panel");
  await actions.getByRole("button", { name: "Sign out everywhere" }).click();
  const dialog = page.getByRole("dialog", { name: /^Sign .* out everywhere\?$/ });
  await expect(dialog).toBeVisible();
  await expectClean(page, "sign-out-everywhere dialog");
  await dialog.getByRole("button", { name: "Cancel" }).click();
});

test("the audit log is accessible with an entry open and when nothing matches", async ({
  page,
}) => {
  await page.goto("/admin/audit");
  await expect(page.getByRole("region", { name: "Audit entries table" })).toBeVisible();
  await page
    .getByRole("button", { name: /^Show details of/ })
    .first()
    .click();
  await expect(page.getByRole("button", { name: /^Hide details of/ }).first()).toHaveAttribute(
    "aria-expanded",
    "true",
  );
  await expectClean(page, "/admin/audit with details open");

  // A day long before the CMS existed: the honest empty state.
  await page.goto("/admin/audit?from=2020-01-01&to=2020-01-01");
  await expect(page.getByText("No entries match these filters")).toBeVisible();
  await expectClean(page, "/admin/audit empty");
});

test("My account is accessible", async ({ page }) => {
  await page.goto("/admin/account");
  await expect(page.getByRole("form", { name: "Change password" })).toBeVisible();
  await page.getByRole("button", { name: "Change password" }).click();
  await expect(page.getByText("Enter your current password.")).toBeVisible();
  await expectClean(page, "/admin/account with errors");
});

test("every Settings section is accessible", async ({ page }) => {
  await page.goto("/admin/settings");
  const tabs = page.getByRole("tablist", { name: "Settings sections" }).getByRole("tab");
  await expect(tabs).toHaveCount(10);
  const count = await tabs.count();
  for (let index = 0; index < count; index += 1) {
    const tab = tabs.nth(index);
    const name = (await tab.textContent()) ?? String(index);
    await tab.click();
    await expect(tab).toHaveAttribute("aria-selected", "true");
    await page.waitForLoadState("networkidle", { timeout: 3000 }).catch(() => undefined);
    await expectClean(page, `Settings: ${name}`);
  }
  // Keyboard: Arrow Down moves to the next section in the vertical list.
  await page.getByRole("tab", { name: /^Company/ }).click();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("tab", { name: /^RERA/ })).toBeFocused();
  await expect(page).toHaveURL(/\?tab=rera$/);
});
