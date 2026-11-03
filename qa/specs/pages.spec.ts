/**
 * Page-builder pages on the public site (task 5.5a, D-045): a page built through the CMS API
 * with one block of most types, published and read at /<slug>; a legal page's DRAFT notice;
 * draft and unknown pages are 404; axe, the enforced CSP and 390 px.
 *
 * No public lead submission (the lead-form block is checked for its form only) and no sign-in.
 * The "home" page is not published here: other specs read "/".
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { apiCall, CMS_STATE, runId } from "../lib/auth";
import { catalogueProject } from "../lib/catalogue";
import { draftPage, libraryPhoto } from "../lib/content";

test.use({ storageState: CMS_STATE });

async function seriousAxe(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.help}`);
}

function watchCsp(page: Page): string[] {
  const violations: string[] = [];
  page.on("console", (msg) => {
    if (/Content Security Policy|violates the following/.test(msg.text())) {
      violations.push(msg.text());
    }
  });
  return violations;
}

async function saveAndPublish(page: Page, pageId: string, blocks: unknown[]): Promise<void> {
  const saved = await apiCall(page, "PUT", `/api/v1/admin/pages/${pageId}/blocks`, { blocks });
  expect(saved.status(), await saved.text()).toBe(200);
  const published = await apiCall(page, "POST", `/api/v1/admin/pages/${pageId}/publish`);
  expect(published.status(), await published.text()).toBe(200);
}

test("a page built from blocks shows every block on the website", async ({ page, browser }) => {
  const id = runId();
  const project = await catalogueProject(page);
  const photo = await libraryPhoto(page, `E2E block photo ${id}`);
  const created = await draftPage(page);
  await saveAndPublish(page, created.id, [
    {
      type: "hero",
      data: {
        eyebrow: "E2E",
        heading: `E2E hero ${id}`,
        subheading: "Homes in Uttar Pradesh",
        image_id: photo,
        cta: { label: "See projects", href: "/projects" },
      },
    },
    {
      type: "rich_text",
      data: { heading: "About us", body: "We *build* homes.\n\n- Honest\n- On time" },
    },
    { type: "image", data: { image_id: photo, caption: "E2E caption" } },
    { type: "gallery", data: { heading: "Gallery", image_ids: [photo] } },
    {
      type: "video",
      data: { heading: "Site tour", url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ" },
    },
    { type: "project_grid", data: { heading: "Our projects", limit: 3 } },
    { type: "property_grid", data: { heading: "Homes", limit: 3 } },
    {
      type: "cta",
      data: { heading: "Talk to us", text: "We call back.", label: "Contact", href: "/contact" },
    },
    {
      type: "lead_form",
      data: { heading: "Ask about it", source: "project_form", project_id: project.id },
    },
    {
      type: "stats",
      data: {
        heading: "In numbers",
        items: [{ value: "12", label: "towers", source: "E2E register", as_of: "2026-09-30" }],
      },
    },
    { type: "map", data: { heading: "Where it is", project_id: project.id } },
    {
      type: "steps",
      data: { heading: "How to book", items: [{ title: "Visit", text: "See the site" }] },
    },
    {
      type: "columns",
      data: {
        columns: [
          { heading: "Left", body: "A" },
          { heading: "Right", body: "B" },
        ],
      },
    },
    { type: "divider", data: {} },
  ]);

  const visitorContext = await browser.newContext();
  const visitor = await visitorContext.newPage();
  const csp = watchCsp(visitor);
  const response = await visitor.goto(`/${created.slug}`);
  expect(response?.status()).toBe(200);
  const main = visitor.locator("#main-content");

  await expect(visitor.getByRole("heading", { level: 1 })).toHaveText(`E2E hero ${id}`);
  await expect(visitor.getByRole("heading", { level: 1 })).toHaveCount(1);
  await expect(main.getByRole("link", { name: "See projects" })).toHaveAttribute(
    "href",
    "/projects",
  );
  await expect(main.locator("strong", { hasText: "build" })).toBeVisible();
  await expect(main.getByText("E2E caption")).toBeVisible();
  await expect(main.getByText("Artist's impression").first()).toBeVisible();
  await expect(main.getByTestId("video-link")).toHaveAttribute(
    "href",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  );
  await expect(main.locator("iframe")).toHaveCount(0);
  await expect(main.getByRole("heading", { name: "Our projects" })).toBeVisible();
  await expect(main.getByTestId("project-card").first()).toBeVisible();
  await expect(main.getByTestId("rera-line").first()).toBeVisible();
  await expect(main.getByRole("link", { name: "Contact", exact: true })).toHaveAttribute(
    "href",
    "/contact",
  );
  await expect(main.getByTestId("lead-form-enquiry")).toBeVisible();
  await expect(main.getByTestId("stat-source")).toHaveText(
    "As of 30 Sep 2026 · Source: E2E register",
  );
  await expect(main.getByRole("button", { name: "Show map" })).toBeVisible();
  await expect(main.getByRole("heading", { name: "How to book" })).toBeVisible();
  await expect(main.getByRole("heading", { name: "Right" })).toBeVisible();

  expect(await seriousAxe(visitor)).toEqual([]);
  expect(csp).toEqual([]);

  await visitor.setViewportSize({ width: 390, height: 844 });
  await visitor.reload();
  const overflow = await visitor.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
  await visitorContext.close();
});

test("a legal page with draft text shows the DRAFT notice", async ({ page }) => {
  const created = await draftPage(page, "legal");
  await saveAndPublish(page, created.id, [
    {
      type: "rich_text",
      data: { body: "[DRAFT — text to be drafted by Claude and approved by the owner; see D-017]" },
    },
  ]);
  await page.goto(`/${created.slug}`);
  await expect(page.getByTestId("legal-draft-notice")).toContainText("DRAFT");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(created.title);
});

test("draft and unknown pages are not found", async ({ page }) => {
  const draft = await draftPage(page);
  for (const path of [`/${draft.slug}`, "/e2e-no-such-page"]) {
    const response = await page.goto(path);
    expect(response?.status(), path).toBe(404);
    await expect(page.getByText("PAGE NOT FOUND")).toBeVisible();
  }
});
