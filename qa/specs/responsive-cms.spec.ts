// Phone width: no CMS page scrolls sideways at 390 × 844 (DESIGN_SYSTEM §1 "readable at night on
// a phone"). Wide tables scroll inside their own region instead of the page. Covers the projects
// list, every editor tab (Media and Documents included), the catalogue and the media library.
import { expect, test, type Locator, type Page } from "@playwright/test";
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

/** `lower` starts below `upper` (stacked, not squeezed side by side). */
async function expectBelow(upper: Locator, lower: Locator, label: string) {
  const a = await upper.boundingBox();
  const b = await lower.boundingBox();
  expect(a && b, label).toBeTruthy();
  if (a && b) expect(b.y, label).toBeGreaterThanOrEqual(a.y + a.height - 1);
}

/** The element is at least `min` px wide and fully on screen horizontally. */
async function expectReadable(page: Page, locator: Locator, min: number, label: string) {
  const box = await locator.boundingBox();
  const width = page.viewportSize()?.width ?? 0;
  expect(box, label).toBeTruthy();
  if (box) {
    expect(box.width, `${label}: width`).toBeGreaterThanOrEqual(min);
    expect(box.x, `${label}: left edge`).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width, `${label}: right edge`).toBeLessThanOrEqual(width);
  }
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

test("the media library fits a phone screen, as a grid and a list", async ({ page }) => {
  await page.goto("/admin/media");
  await expect(page.getByRole("heading", { level: 1, name: "Media" })).toBeVisible();
  await expect(page.getByRole("search", { name: "Filter media" })).toBeVisible();
  await expectNoSideScroll(page, "/admin/media");
  await expectReadable(page, page.getByLabel("Search"), 180, "library search field");
  await expectReadable(page, page.getByRole("radiogroup", { name: "View" }), 100, "View switcher");
  await page.goto("/admin/media?view=list");
  await expect(page.getByRole("radio", { name: "List" })).toHaveAttribute("aria-checked", "true");
  await expectNoSideScroll(page, "/admin/media?view=list");
});

test("the Media, Documents and SEO tabs stack their headers on a phone", async ({ page }) => {
  await page.goto("/admin/projects?q=sample-project-a");
  await page.getByRole("link", { name: "Sample — Project A" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Sample — Project A" })).toBeVisible();
  const base = page.url().split("?")[0];

  // Media: the Photos/Videos/Documents switcher sits under the title, which keeps its width.
  await page.goto(`${base}?tab=media`);
  const media = page.getByRole("tabpanel", { name: "Media", exact: true });
  const title = media.getByRole("heading", { name: "Media manager" });
  const switcher = media.getByRole("radiogroup", { name: "Media type" });
  await expect(switcher).toBeVisible();
  await expectBelow(title, switcher, "Media type switcher under the title");
  await expectReadable(page, title.locator(".."), 250, "Media manager title block");
  await expectReadable(page, switcher, 200, "Media type switcher");
  await expectReadable(
    page,
    media.getByRole("button", { name: "Drag files here or browse" }),
    150,
    "drop zone button",
  );
  await expectNoSideScroll(page, "editor tab Media");

  // Documents: the QR panel's text and its upload button are readable and on screen.
  await page.goto(`${base}?tab=documents`);
  const documents = page.getByRole("tabpanel", { name: "Documents", exact: true });
  await expectReadable(
    page,
    documents.getByText("RERA QR code image · missing"),
    150,
    "QR status text",
  );
  await expectReadable(
    page,
    documents.getByRole("button", { name: "Upload QR image" }),
    100,
    "Upload QR image",
  );
  await expectReadable(
    page,
    documents.getByRole("button", { name: "Upload brochure (PDF)" }),
    100,
    "Upload brochure",
  );
  await expectNoSideScroll(page, "editor tab Documents");

  // SEO: the share image choices fit.
  await page.goto(`${base}?tab=seo`);
  const seo = page.getByRole("tabpanel", { name: "SEO", exact: true });
  await expectReadable(
    page,
    seo.getByRole("group", { name: "Choose from this project's photos" }),
    250,
    "share image choices",
  );
  await expectNoSideScroll(page, "editor tab SEO");
});
