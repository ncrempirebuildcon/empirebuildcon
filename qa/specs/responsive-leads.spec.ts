// Phone width (390 × 844) for the lead screens (spec Phase 4 part 3 §7): no page scrolls sideways
// on the dashboard, the inbox (table and board), a lead's detail, the site-visit calendar and the
// UTM report; the calendar opens in its list view on a phone; tap targets on the lead detail are
// at least 44 px tall.
import { expect, test, type Page } from "@playwright/test";
import { CMS_STATE, runId } from "../lib/auth";
import { manualLead } from "../lib/leads";

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

test("the dashboard and the inbox fit a phone screen", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByRole("list", { name: "Counts" })).toBeVisible();
  await expectNoSideScroll(page, "/admin");

  await page.goto("/admin/leads");
  await expect(page.getByRole("table", { name: "Leads, newest first" })).toBeVisible();
  await expectNoSideScroll(page, "/admin/leads");
  await page.goto("/admin/leads?view=board");
  await expect(page.getByRole("region", { name: /^New/ })).toBeVisible();
  await expectNoSideScroll(page, "/admin/leads?view=board");
});

test("a lead's detail fits a phone screen, with 44 px tap targets", async ({ page }) => {
  const name = `E2E Phone ${runId()}`;
  const lead = await manualLead(page, name);
  await page.goto(`/admin/leads/${lead.id}`);
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  await expectNoSideScroll(page, "lead detail");

  const main = page.locator("main");
  const targets = main.locator("button:visible, a:visible, select:visible, input:visible");
  const small: string[] = [];
  for (const target of await targets.all()) {
    const box = await target.boundingBox();
    const inSentence = await target.evaluate(
      (node) => node.tagName === "A" && node.closest("p, dd, li") !== null,
    );
    // WHY sentences are skipped: a link inside a line of text is exempt (WCAG 2.5.8 "inline").
    if (box && !inSentence && box.height < 44) {
      small.push(
        `${await target.evaluate((node) => node.outerHTML.slice(0, 80))} (${box.height}px)`,
      );
    }
  }
  expect(small).toEqual([]);
});

test("the site-visit calendar opens as a list on a phone and fits the screen", async ({ page }) => {
  await page.goto("/admin/site-visits");
  await expect(page.getByRole("radio", { name: "List" })).toHaveAttribute("aria-checked", "true");
  await expectNoSideScroll(page, "/admin/site-visits (list)");
  await page.goto("/admin/site-visits?view=week");
  await expect(page.getByRole("table", { name: /^Site visits, / })).toBeVisible();
  // The week is wide; it scrolls inside its own region, never the page.
  await expectNoSideScroll(page, "/admin/site-visits?view=week");
  await page.goto("/admin/site-visits?view=day");
  await expectNoSideScroll(page, "/admin/site-visits?view=day");
});

test("the UTM report fits a phone screen", async ({ page }) => {
  await page.goto("/admin/reports/utm");
  await expect(page.getByRole("table", { name: /^Leads by / })).toBeVisible();
  await expectNoSideScroll(page, "/admin/reports/utm");
});
