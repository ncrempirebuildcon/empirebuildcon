// Accessibility of the content screens (Phase 4 part 4): axe finds no serious or critical WCAG
// 2.1 A/AA issues on the pages list, the new-page form, the page editor (every tab, the block
// palette, a form for every block type, the delete dialog), the posts list and editor, offers,
// FAQs, testimonials and redirects with their editors open, and the project editor's FAQs tab.
import { expect, test, type Page } from "@playwright/test";
import { CMS_STATE, apiCall, runId, seriousA11yViolations } from "../lib/auth";
import { draftPage } from "../lib/content";

test.use({ storageState: CMS_STATE });

async function expectClean(page: Page, label: string) {
  // WHY: Next.js streams page metadata, so the <title> can arrive just after the content; axe
  // would report a missing title that a moment later is there.
  await expect(page).toHaveTitle(/\S/);
  expect(await seriousA11yViolations(page), label).toEqual([]);
}

test("the pages list and the new-page form are accessible", async ({ page }) => {
  await page.goto("/admin/pages");
  await expect(page.getByRole("table", { name: "Pages" })).toBeVisible();
  await expectClean(page, "/admin/pages");
  await page.goto("/admin/pages/new");
  await expect(page.getByRole("textbox", { name: /^Title/ })).toBeVisible();
  await expectClean(page, "/admin/pages/new");
});

test("the page editor, its palette and every block form are accessible", async ({ page }) => {
  // WHY: axe runs on about 20 states of a heavy editor here; 30 s was tight on a busy machine.
  test.setTimeout(90_000);
  const draft = await draftPage(page, "landing");
  await page.goto(`/admin/pages/${draft.id}`);
  await expect(page.getByRole("tablist", { name: "Page sections" })).toBeVisible();
  await expectClean(page, "empty Blocks tab");

  await page.getByRole("button", { name: "+ Add block" }).click();
  const palette = page.getByRole("dialog", { name: "Add a block" });
  await expect(palette).toBeVisible();
  await expectClean(page, "block palette");
  const names = (await palette.locator("li button > span:first-child").allTextContents()).map((n) =>
    n.trim(),
  );
  expect(names.length).toBe(17);
  await palette.getByRole("button", { name: "Cancel" }).click();

  // One block of every type, each form checked while it is selected.
  for (const name of names) {
    await page.getByRole("button", { name: "+ Add block" }).click();
    await page
      .getByRole("dialog", { name: "Add a block" })
      .getByRole("button", { name: new RegExp(`^${name} `) })
      .click();
    await expect(
      page.getByRole("heading", { level: 2, name: new RegExp(`^${name} · block`) }),
    ).toBeVisible();
    await expectClean(page, `${name} block form`);
  }

  // The checks after a refused save (empty required fields) are labelled and linked too.
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Some fields need attention." }),
  ).toBeVisible();
  await expectClean(page, "block errors");

  await page.getByRole("button", { name: /^Delete block \d+: / }).click();
  await expect(page.getByRole("dialog", { name: /^Delete this/ })).toBeVisible();
  await expectClean(page, "delete block dialog");
  await page.getByRole("button", { name: "Cancel" }).click();

  for (const tab of ["Settings", "SEO"]) {
    await page.getByRole("tab", { name: tab }).click();
    await expect(page.getByRole("tabpanel", { name: tab })).toBeVisible();
    await expectClean(page, `${tab} tab`);
  }
});

test("a seeded legal page with its DRAFT banner is accessible", async ({ page }) => {
  const response = await apiCall(page, "GET", "/api/v1/admin/pages?kind=legal&per_page=10");
  const { items } = (await response.json()) as { items: Array<{ id: string }> };
  expect(items.length).toBeGreaterThan(0);
  await page.goto(`/admin/pages/${items[0]?.id}`);
  await expect(page.getByRole("note", { name: "Legal page" })).toBeVisible();
  await expectClean(page, "legal page");
});

test("the posts list and the post editor are accessible", async ({ page }) => {
  await page.goto("/admin/posts");
  await expect(page.getByRole("navigation", { name: "Offers & blog sections" })).toBeVisible();
  await expectClean(page, "/admin/posts");
  await page.goto("/admin/posts/new");
  await page.getByRole("textbox", { name: /^Title/ }).fill(`E2E A11y post ${runId()}`);
  await expectClean(page, "new post");
  await page.getByRole("button", { name: "Choose from the library: Cover image" }).click();
  await expect(page.getByRole("dialog", { name: "Choose a photo from the library" })).toBeVisible();
  await expectClean(page, "library picker");
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
  await page.getByRole("tab", { name: "SEO" }).click();
  await expectClean(page, "post SEO tab");
});

test("offers, FAQs, testimonials and redirects are accessible with their editors open", async ({
  page,
}) => {
  await page.goto("/admin/offers");
  await page.getByRole("button", { name: "+ New offer" }).click();
  await expect(page.getByRole("region", { name: "New offer" })).toBeVisible();
  await expectClean(page, "/admin/offers");

  await page.goto("/admin/faqs");
  await expect(page.getByRole("heading", { level: 2, name: "Site-wide FAQs" })).toBeVisible();
  await page.getByRole("button", { name: "+ Add FAQ" }).click();
  await expect(page.getByRole("form", { name: "Add FAQ" })).toBeVisible();
  await expectClean(page, "/admin/faqs");

  await page.goto("/admin/testimonials");
  await page.getByRole("button", { name: "+ Add testimonial" }).click();
  await expect(page.getByRole("region", { name: "Add a testimonial" })).toBeVisible();
  await expectClean(page, "/admin/testimonials");

  await page.goto("/admin/redirects");
  await page.getByRole("button", { name: "+ New redirect" }).click();
  await expect(page.getByRole("region", { name: "New redirect" })).toBeVisible();
  await expectClean(page, "/admin/redirects");
});

test("the project editor's FAQs tab is accessible", async ({ page }) => {
  const created = await apiCall(page, "POST", "/api/v1/admin/projects", {
    name: `E2E A11y FAQs ${runId()}`,
    status: "upcoming",
  });
  const { id } = (await created.json()) as { id: string };
  await page.goto(`/admin/projects/${id}?tab=faqs`);
  await expect(page.getByRole("tabpanel", { name: "FAQs" })).toBeVisible();
  await page.getByRole("button", { name: "+ Add FAQ" }).click();
  await expect(page.getByRole("form", { name: "Add FAQ" })).toBeVisible();
  await expectClean(page, "project FAQs tab");
});
