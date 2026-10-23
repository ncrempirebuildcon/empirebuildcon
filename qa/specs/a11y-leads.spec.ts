// Accessibility of the lead screens (spec Phase 4 part 3 §7): axe finds no serious or critical
// WCAG 2.1 A/AA issues on the dashboard, the inbox (table, board, Add lead and Export dialogs),
// a lead's detail (with the Lost reason and Erase dialogs), the site-visit calendar (week, day and
// list, with a visit open) and the UTM report. Also: the board's "Move to" works from the
// keyboard and is announced, and the calendar's visits are reachable with Tab.
import { expect, test, type Page } from "@playwright/test";
import { CMS_STATE, apiCall, runId, seriousA11yViolations } from "../lib/auth";
import { manualLead } from "../lib/leads";

// Signed in once by auth.setup.ts (the API limits sign-ins per network).
test.use({ storageState: CMS_STATE });

async function expectNoViolations(page: Page, label: string) {
  expect(await seriousA11yViolations(page), label).toEqual([]);
}

test("the dashboard has no serious accessibility violations", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByRole("heading", { level: 2, name: "At a glance" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Counts" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Leads by source" })).not.toContainText("Loading");
  await expectNoViolations(page, "/admin");
});

test("the inbox, its board and dialogs have no serious accessibility violations", async ({
  page,
}) => {
  await manualLead(page, `E2E A11y Inbox ${runId()}`);
  await page.goto("/admin/leads");
  await expect(page.getByRole("table", { name: "Leads, newest first" })).toBeVisible();
  await expectNoViolations(page, "inbox table");

  await page.getByRole("button", { name: "+ Add lead" }).click();
  const add = page.getByRole("dialog", { name: "Add a lead" });
  await expect(add).toBeVisible();
  // The consent note is required: an empty form says so next to the field.
  await add.getByRole("button", { name: "Add lead" }).click();
  await expect(add.getByText(/Say how they agreed to be contacted/)).toBeVisible();
  await expectNoViolations(page, "Add lead dialog");
  await add.getByRole("button", { name: "Cancel" }).click();

  await page.getByRole("button", { name: "Export CSV" }).click();
  const exporting = page.getByRole("dialog", { name: "Export these leads?" });
  await expect(exporting).toBeVisible();
  await expectNoViolations(page, "Export dialog");
  await exporting.getByRole("button", { name: "Cancel" }).click();

  await page.getByRole("radio", { name: "Board" }).click();
  await expect(page).toHaveURL(/view=board/);
  await expect(page.getByRole("region", { name: /^New/ })).toBeVisible();
  await expectNoViolations(page, "inbox board");
});

test("the board's Move to works from the keyboard and is announced", async ({ page }) => {
  const name = `E2E Board ${runId()}`;
  const lead = await manualLead(page, name);
  await page.goto(`/admin/leads?view=board&q=${encodeURIComponent(name)}`);
  const newColumn = page.getByRole("region", { name: /^New/ });
  const card = newColumn.getByRole("article", { name });
  await expect(card).toBeVisible();

  // Moving to Lost asks for a reason first.
  const move = card.getByLabel(`Move to, ${name}`);
  await move.focus();
  await move.selectOption({ label: "Lost" });
  const dialog = page.getByRole("dialog", { name: `Mark ${name} as lost?` });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Mark lost" }).click();
  await expect(dialog.getByText("Pick a reason to mark this lead lost.")).toBeVisible();
  await expectNoViolations(page, "Lost dialog on the board");
  await dialog.getByRole("button", { name: "Cancel" }).click();

  await move.selectOption({ label: "Contacted" });
  await expect(
    page.getByRole("status").filter({ hasText: `${name} moved to Contacted.` }),
  ).toBeAttached();
  const contacted = page.getByRole("region", { name: /^Contacted/ });
  await expect(contacted.getByRole("article", { name })).toBeVisible();
  // Focus stays on the moved card, now in its new column.
  await expect(contacted.getByLabel(`Move to, ${name}`)).toBeFocused();
  const saved = await apiCall(page, "GET", `/api/v1/admin/leads/${lead.id}`);
  expect(((await saved.json()) as { status: string }).status).toBe("contacted");
});

test("a lead's detail and its dialogs have no serious accessibility violations", async ({
  page,
}) => {
  const name = `E2E A11y Lead ${runId()}`;
  const lead = await manualLead(page, name);
  await page.goto(`/admin/leads/${lead.id}`);
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  await expect(page.getByRole("list", { name: "Timeline, newest first" })).toBeVisible();
  await expectNoViolations(page, "lead detail");

  // Lost needs a reason: the form says so, and the error is linked to the field.
  await page
    .getByRole("group", { name: "Choose a stage" })
    .getByRole("button", { name: "Lost" })
    .click();
  await page.getByRole("button", { name: "Save stage" }).click();
  await expect(page.getByText("Pick a reason to mark this lead lost.")).toBeVisible();
  await expect(page.getByLabel("Reason")).toHaveAttribute("aria-invalid", "true");
  await expectNoViolations(page, "lead detail, lost reason");
  await page.getByRole("button", { name: "Cancel" }).click();

  await page.getByRole("button", { name: "Edit details" }).click();
  await expect(page.getByRole("form", { name: "Edit enquiry details" })).toBeVisible();
  await expectNoViolations(page, "lead detail, edit details");
  await page
    .getByRole("form", { name: "Edit enquiry details" })
    .getByRole("button", { name: "Cancel" })
    .click();

  await page.getByRole("button", { name: "Erase personal data" }).click();
  await expect(page.getByRole("dialog", { name: "Erase this person's data?" })).toBeVisible();
  await expectNoViolations(page, "erase dialog");
  await page.getByRole("button", { name: "Keep the data" }).click();
});

test("a sample lead shows its SAMPLE note and site visit", async ({ page }) => {
  // The sample seed adds leads with visits (dev/test only); open one that has a visit.
  const response = await apiCall(page, "GET", "/api/v1/admin/site-visits");
  expect(response.status()).toBe(200);
  const visits = (await response.json()) as Array<{ lead_id: string; is_sample: boolean }>;
  const sample = visits.find((visit) => visit.is_sample);
  test.skip(!sample, "no sample visits in this database");
  await page.goto(`/admin/leads/${sample?.lead_id}`);
  await expect(page.getByRole("note").filter({ hasText: "Sample data" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Site visit", exact: true })).toBeVisible();
  await expectNoViolations(page, "sample lead with a visit");
});

test("the site-visit calendar has no serious accessibility violations in any view", async ({
  page,
}) => {
  await page.goto("/admin/site-visits?view=week");
  await expect(page.getByRole("radio", { name: "Week" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("table", { name: /^Site visits, / })).toBeVisible();
  await expectNoViolations(page, "calendar week");

  // Keyboard: Tab from "Next week" reaches the view switcher, then the visits.
  await page.getByRole("button", { name: "Next week" }).focus();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Today" })).toBeFocused();

  await page.getByRole("radio", { name: "Day" }).click();
  await expect(page).toHaveURL(/view=day/);
  await expectNoViolations(page, "calendar day");

  await page.getByRole("radio", { name: "List" }).click();
  await expect(page).toHaveURL(/view=list/);
  await expect(page.getByRole("table", { name: /^Site visits, / })).toBeVisible();
  await expectNoViolations(page, "calendar list");

  // With a visit open in the side panel (a sample visit, if this week has one).
  const first = page
    .getByRole("table", { name: /^Site visits, / })
    .getByRole("button")
    .first();
  if (await first.count()) {
    await first.click();
    await expect(page.getByRole("heading", { level: 2, name: "No visit selected" })).toHaveCount(0);
    await expect(page.locator("#selected-visit")).toBeFocused();
    await expectNoViolations(page, "calendar with a visit open");
  }
});

test("the UTM report has no serious accessibility violations", async ({ page }) => {
  await page.goto("/admin/reports/utm");
  await expect(page.getByRole("heading", { level: 1, name: "UTM report" })).toBeVisible();
  await expect(page.getByRole("table", { name: /^Leads by / })).toBeVisible();
  await expectNoViolations(page, "UTM report");
  await page.getByLabel("Group by").selectOption({ label: "Campaign only" });
  await page.getByRole("button", { name: "Show report" }).click();
  await expect(page).toHaveURL(/group_by=campaign/);
  await expect(page.getByRole("table", { name: "Leads by campaign" })).toBeVisible();
  await expectNoViolations(page, "UTM report by campaign");
});
