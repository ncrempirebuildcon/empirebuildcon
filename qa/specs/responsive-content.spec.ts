// Phone width (390 × 844): no sideways page scroll on the content screens (Phase 4 part 4):
// pages, the page editor with blocks of several kinds and every tab, posts, offers, FAQs,
// testimonials and redirects. Wide tables scroll inside their own region instead of the page.
import { expect, test, type Page } from "@playwright/test";
import { CMS_STATE, apiCall } from "../lib/auth";
import { draftPage } from "../lib/content";

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

test("the content lists fit a phone screen", async ({ page }) => {
  for (const path of [
    "/admin/pages",
    "/admin/pages/new",
    "/admin/posts",
    "/admin/posts/new",
    "/admin/offers",
    "/admin/faqs",
    "/admin/testimonials",
    "/admin/redirects",
  ]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    // WHY: the lists load in the browser after the shell; measure once they have arrived.
    await page.waitForLoadState("networkidle");
    await expectNoSideScroll(page, path);
  }
});

test("the editors fit a phone screen with their forms open", async ({ page }) => {
  await page.goto("/admin/offers");
  await page.getByRole("button", { name: "+ New offer" }).click();
  await expect(page.getByRole("region", { name: "New offer" })).toBeVisible();
  await expectNoSideScroll(page, "offer editor");

  await page.goto("/admin/testimonials");
  await page.getByRole("button", { name: "+ Add testimonial" }).click();
  await expect(page.getByRole("region", { name: "Add a testimonial" })).toBeVisible();
  await expectNoSideScroll(page, "testimonial editor");

  await page.goto("/admin/redirects");
  await page.getByRole("button", { name: "+ New redirect" }).click();
  await expect(page.getByRole("region", { name: "New redirect" })).toBeVisible();
  await expectNoSideScroll(page, "redirect editor");

  await page.goto("/admin/faqs");
  await page.getByRole("button", { name: "+ Add FAQ" }).click();
  await expect(page.getByRole("form", { name: "Add FAQ" })).toBeVisible();
  await expectNoSideScroll(page, "FAQ form");
});

test("the page editor fits a phone screen, with blocks and on every tab", async ({ page }) => {
  const draft = await draftPage(page);
  // Blocks with wide content: numbers, columns, steps and a hero with two buttons.
  const saved = await apiCall(page, "PUT", `/api/v1/admin/pages/${draft.id}/blocks`, {
    blocks: [
      {
        type: "hero",
        data: {
          eyebrow: "[EYEBROW]",
          heading: "E2E hero heading for a phone",
          subheading: null,
          image_id: null,
          cta: { label: "E2E first", href: "/projects" },
          secondary_cta: { label: "E2E second", href: "/contact" },
        },
      },
      {
        type: "columns",
        data: {
          heading: null,
          columns: [
            { heading: "E2E one", body: "- a\n  - b" },
            { heading: "E2E two", body: "*c*" },
            { heading: "E2E three", body: "_d_" },
          ],
        },
      },
    ],
  });
  expect(saved.status(), await saved.text()).toBe(200);
  await page.goto(`/admin/pages/${draft.id}`);
  await expect(
    page.getByRole("list", { name: "Blocks in page order" }).getByRole("listitem"),
  ).toHaveCount(2);
  await expectNoSideScroll(page, "blocks tab (hero)");
  await page.getByRole("button", { name: /^2\. Columns/ }).click();
  await expectNoSideScroll(page, "blocks tab (columns)");
  await page.getByRole("radio", { name: "Mobile" }).click();
  await expectNoSideScroll(page, "mobile preview");
  for (const tab of ["Settings", "SEO"]) {
    await page.getByRole("tab", { name: tab }).click();
    await expect(page.getByRole("tabpanel", { name: tab })).toBeVisible();
    await expectNoSideScroll(page, `${tab} tab`);
  }
});
