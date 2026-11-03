/**
 * Every dashboard count opens a list with the same total (D-034).
 *
 * WHY in the "serial" project (playwright.config.ts): the counts and the lists are read one
 * after the other, and other specs create, publish and archive projects and leads at the same
 * time; in the main project a count could change in between (it happened on 3 Nov 2026 once
 * the catalogue and lead-form specs joined the suite). Here nothing else runs, so the exact
 * comparison stays exact. Moved from leads.spec.ts unchanged.
 */
import { expect, test } from "@playwright/test";
import { CMS_STATE, apiCall } from "../lib/auth";

test.use({ storageState: CMS_STATE });

test("every dashboard count matches the list its link opens", async ({ page }) => {
  const response = await apiCall(page, "GET", "/api/v1/admin/dashboard");
  const { counts } = (await response.json()) as {
    counts: Array<{ key: string; label: string; count: number; link: string }>;
  };
  expect(counts.length).toBeGreaterThan(0);
  for (const count of counts) {
    await page.goto("/admin");
    await page
      .getByRole("list", { name: "Counts" })
      .getByRole("link", { name: new RegExp(`^${escapeRegExp(count.label)} ${count.count} `) })
      .click();
    await expect(page).toHaveURL(new RegExp(`${escapeRegExp(count.link)}$`));
    if (count.link.startsWith("/admin/site-visits")) {
      const noun = count.count === 1 ? "visit" : "visits";
      await expect(page.getByText(new RegExp(`^${count.count} ${noun} · `))).toBeVisible();
    } else {
      const noun = count.link.startsWith("/admin/projects") ? "project" : "lead";
      const pager = page.getByRole("navigation", { name: new RegExp(`^Pages of ${noun}s`) });
      await expect(pager.getByRole("status")).toHaveText(
        count.count === 0
          ? `No ${noun}s`
          : new RegExp(`of ${count.count} ${count.count === 1 ? noun : `${noun}s`}$`),
      );
    }
  }
});

/** `text` as a literal inside a regular expression. */
function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
