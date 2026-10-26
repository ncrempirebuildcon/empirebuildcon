// Object-level access to leads (spec Phase 4 part 3, QA journey 2; SECURITY.md §1): a sales user
// sees only the leads they own, in the inbox, the detail page, notes and activity, and someone
// else's lead answers 404, exactly like a lead that doesn't exist. They get no export.
//
// Sign-in budget: the sales user signed in once in auth.setup.ts (SALES_STATE); this spec signs
// in nobody. A full run signs in 4 times (2 in the setup project, 2 in login.spec.ts).
import { expect, test, type Browser } from "@playwright/test";
import { CMS_STATE, SALES_STATE, runId } from "../lib/auth";
import { manualLead } from "../lib/leads";

test.use({ storageState: CMS_STATE });

/** A page signed in as the sales user (their saved session), and their user id. */
async function salesPage(browser: Browser) {
  const context = await browser.newContext({ storageState: SALES_STATE });
  const page = await context.newPage();
  const me = await page.request.get("/api/v1/auth/me");
  expect(me.status()).toBe(200);
  const { id } = (await me.json()) as { id: string };
  return { context, page, id };
}

test("a sales user sees only their own leads", async ({ page, browser }) => {
  const sales = await salesPage(browser);
  const run = runId();
  const mine = await manualLead(page, `E2E Mine ${run}`, sales.id);
  const theirs = await manualLead(page, `E2E Theirs ${run}`, null);

  try {
    // The API: the list holds only their lead; the other one is "not found" everywhere.
    const list = await sales.page.request.get(`/api/v1/admin/leads?q=${encodeURIComponent(run)}`);
    expect(list.status()).toBe(200);
    const { items } = (await list.json()) as { items: Array<{ id: string }> };
    expect(items.map((item) => item.id)).toEqual([mine.id]);
    for (const path of ["", "/notes", "/activity"]) {
      const other = await sales.page.request.get(`/api/v1/admin/leads/${theirs.id}${path}`);
      expect(other.status(), `GET …/${theirs.id}${path}`).toBe(404);
      const own = await sales.page.request.get(`/api/v1/admin/leads/${mine.id}${path}`);
      expect(own.status(), `GET …/${mine.id}${path}`).toBe(200);
    }
    const exported = await sales.page.request.get("/api/v1/admin/leads/export.csv");
    expect(exported.status()).toBe(403);

    // The CMS: the inbox lists only their lead, with no Owner filter and no Export button.
    await sales.page.goto(`/admin/leads?q=${run}`);
    const table = sales.page.getByRole("table", { name: "Leads, newest first" });
    await expect(table.getByRole("rowheader")).toHaveCount(1);
    await expect(table).toContainText(`E2E Mine ${run}`);
    await expect(table).not.toContainText(`E2E Theirs ${run}`);
    await expect(sales.page.getByRole("button", { name: "Export CSV" })).toHaveCount(0);
    await expect(sales.page.getByLabel("Owner", { exact: true })).toHaveCount(0);

    // Their own lead opens; someone else's says it isn't available, like a missing one.
    await sales.page.goto(`/admin/leads/${mine.id}`);
    await expect(
      sales.page.getByRole("heading", { level: 1, name: `E2E Mine ${run}` }),
    ).toBeVisible();
    await expect(sales.page.getByRole("button", { name: "Erase personal data" })).toHaveCount(0);
    await sales.page.goto(`/admin/leads/${theirs.id}`);
    await expect(sales.page.getByText("This lead isn't available.")).toBeVisible();
    await expect(sales.page.getByText(`E2E Theirs ${run}`)).toHaveCount(0);

    // The super-admin sees both.
    await page.goto(`/admin/leads?q=${run}`);
    await expect(
      page.getByRole("table", { name: "Leads, newest first" }).getByRole("rowheader"),
    ).toHaveCount(2);
  } finally {
    await sales.context.close();
  }
});
