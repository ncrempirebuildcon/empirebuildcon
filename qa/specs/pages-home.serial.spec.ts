/**
 * The CMS's "home" and "contact" pages on the website (task 5.5a, D-045): each is given blocks,
 * published and read at "/" and "/contact", then its blocks and publish state are put back.
 * Publishing leaves a first-publish date, a redirect claim on its path and audit rows behind;
 * that is harmless for system pages, which are never deleted.
 *
 * WHY the "serial" project (playwright.config.ts): other specs read "/" and "/contact" and expect
 * them as seeded, so this runs only after the main project has finished.
 */
import { expect, type Page, test } from "@playwright/test";
import { apiCall, CMS_STATE, runId } from "../lib/auth";
import { drainOutbox } from "../lib/catalogue";

test.use({ storageState: CMS_STATE });
test.describe.configure({ mode: "serial" });

interface AdminBlock {
  type: string;
  data: Record<string, unknown>;
  is_visible: boolean;
}
interface AdminPage {
  id: string;
  slug: string;
  title: string;
  publish_state: string;
  blocks: AdminBlock[];
}

async function systemPage(page: Page, slug: string): Promise<AdminPage> {
  const list = await apiCall(page, "GET", `/api/v1/admin/pages?q=${slug}&per_page=50`);
  expect(list.status()).toBe(200);
  const { items } = (await list.json()) as { items: { id: string; slug: string }[] };
  const found = items.find((item) => item.slug === slug);
  expect(found, `the seeded "${slug}" page`).toBeTruthy();
  const detail = await apiCall(page, "GET", `/api/v1/admin/pages/${found?.id}`);
  expect(detail.status()).toBe(200);
  return (await detail.json()) as AdminPage;
}

async function putBlocks(page: Page, id: string, blocks: AdminBlock[]): Promise<void> {
  const saved = await apiCall(page, "PUT", `/api/v1/admin/pages/${id}/blocks`, {
    blocks: blocks.map(({ type, data, is_visible }) => ({ type, data, is_visible })),
  });
  expect(saved.status(), await saved.text()).toBe(200);
}

async function setPublished(page: Page, id: string, published: boolean): Promise<void> {
  const action = published ? "publish" : "unpublish";
  const response = await apiCall(page, "POST", `/api/v1/admin/pages/${id}/${action}`);
  expect(response.status(), await response.text()).toBe(200);
}

/**
 * Gives a system page blocks, publishes it, runs `check`, and always puts the blocks and publish
 * state back, even when a step or the check fails.
 */
async function withBlocks(
  page: Page,
  slug: string,
  blocks: AdminBlock[],
  check: () => Promise<void>,
): Promise<void> {
  const before = await systemPage(page, slug);
  expect(
    before.blocks.some((b) => JSON.stringify(b.data).includes("E2E")),
    `"${slug}" still holds blocks from an earlier failed run`,
  ).toBe(false);
  try {
    await putBlocks(page, before.id, blocks);
    await setPublished(page, before.id, true);
    await drainOutbox(page);
    await check();
  } finally {
    await putBlocks(page, before.id, before.blocks);
    await setPublished(page, before.id, before.publish_state === "published");
    await drainOutbox(page);
  }
}

test("the home page shows its CMS blocks at /", async ({ page, browser }) => {
  const id = runId();
  await withBlocks(
    page,
    "home",
    [
      {
        type: "hero",
        data: { heading: `E2E home hero ${id}`, cta: { label: "See projects", href: "/projects" } },
        is_visible: true,
      },
      { type: "rich_text", data: { body: `E2E home text ${id}` }, is_visible: true },
    ],
    async () => {
      const visitorContext = await browser.newContext();
      const visitor = await visitorContext.newPage();
      const response = await visitor.goto("/");
      expect(response?.status()).toBe(200);
      await expect(visitor.getByRole("heading", { level: 1 })).toHaveText(`E2E home hero ${id}`);
      await expect(visitor.getByText(`E2E home text ${id}`)).toBeVisible();
      await expect(visitor.getByText("Our new website is on its way")).toHaveCount(0);
      // The home page's title stands alone, without the "· Empire" suffix (task 5.6).
      expect(await visitor.title()).toBe("Home");
      await visitorContext.close();
    },
  );
});

test("the contact page shows its CMS blocks under the forms, without a hero", async ({
  page,
  browser,
}) => {
  const id = runId();
  await withBlocks(
    page,
    "contact",
    [
      { type: "hero", data: { heading: `E2E contact hero ${id}` }, is_visible: true },
      {
        type: "rich_text",
        data: { heading: "Office hours", body: `E2E contact text ${id}` },
        is_visible: true,
      },
    ],
    async () => {
      const visitorContext = await browser.newContext();
      const visitor = await visitorContext.newPage();
      await visitor.goto("/contact");
      await expect(visitor.getByText(`E2E contact text ${id}`)).toBeVisible();
      await expect(visitor.getByText(`E2E contact hero ${id}`)).toHaveCount(0);
      await expect(visitor.getByRole("heading", { level: 1 })).toHaveCount(1);
      await visitorContext.close();
    },
  );
});
