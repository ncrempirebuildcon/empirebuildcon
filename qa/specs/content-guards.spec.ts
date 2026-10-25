// The page editor's guards from the Phase 4 part 4 review (handbook ARCHITECTURE §6, §11):
//   - M2: a live page can't be given a publish time, and taking it down clears its schedule;
//   - L7: a save based on an older version of the page is refused, and the editor offers a reload;
//   - L8: pages that come with the website (here a seeded legal page) keep their address and can't
//     be archived or deleted;
//   - M4: a FAQs block whose last picked FAQ is deleted is hidden, and the editor says why.
// H2 (a scheduled legal page is read-only without legal.publish) needs a role this suite can't
// sign in as, so apps/web/test/pages.test.ts covers the editor's rule and the API tests the rest.
//
// No new sign-ins and no public submissions: the saved super-admin session is reused and the
// setup goes through the staff API (qa/README.md).
import { expect, test, type Page } from "@playwright/test";
import { CMS_STATE, apiCall, runId, seriousA11yViolations } from "../lib/auth";
import { draftPage, seededLegalPage } from "../lib/content";

test.use({ storageState: CMS_STATE });

const inDays = (days: number) => new Date(Date.now() + days * 86_400_000).toISOString();

const status = (page: Page, text: string | RegExp) =>
  page.getByRole("status").filter({ hasText: text });

async function expectClean(page: Page, label: string) {
  await expect(page).toHaveTitle(/\S/);
  expect(await seriousA11yViolations(page), label).toEqual([]);
}

test("a live page takes no publish time, and unpublishing clears its schedule", async ({
  page,
}) => {
  const draft = await draftPage(page);
  const takeDown = await apiCall(page, "PATCH", `/api/v1/admin/pages/${draft.id}`, {
    unpublish_at: inDays(3),
  });
  expect(takeDown.status(), await takeDown.text()).toBe(200);
  const published = await apiCall(page, "POST", `/api/v1/admin/pages/${draft.id}/publish`);
  expect(published.status(), await published.text()).toBe(200);

  await page.goto(`/admin/pages/${draft.id}?tab=settings`);
  const publishOn = page.getByRole("group", { name: "Publish on" });
  const takeDownOn = page.getByRole("group", { name: "Take down on" });
  await expect(publishOn.getByLabel("Date")).toBeDisabled();
  await expect(
    publishOn.getByText("The page is live already. To publish it again on a date, unpublish it"),
  ).toBeVisible();
  // The take-down time stays editable on a live page.
  await expect(takeDownOn.getByLabel("Date")).toBeEnabled();
  await expect(takeDownOn.getByLabel("Date")).not.toHaveValue("");

  // The API refuses a publish time on a live page too.
  const refused = await apiCall(page, "PATCH", `/api/v1/admin/pages/${draft.id}`, {
    publish_at: inDays(2),
  });
  expect(refused.status()).toBe(422);
  expect(((await refused.json()) as { errors: Array<{ field: string }> }).errors[0]?.field).toBe(
    "publish_at",
  );

  // Taking it down clears the schedule, and the fields show it without a reload.
  await page.getByRole("button", { name: "Unpublish" }).click();
  await page
    .getByRole("dialog", { name: "Unpublish this page?" })
    .getByRole("button", { name: "Unpublish" })
    .click();
  await expect(status(page, /^Unpublished\. The page is back to draft/)).toBeVisible();
  await expect(publishOn.getByLabel("Date")).toBeEnabled();
  await expect(takeDownOn.getByLabel("Date")).toHaveValue("");
  const read = await apiCall(page, "GET", `/api/v1/admin/pages/${draft.id}`);
  const saved = (await read.json()) as { publish_at: string | null; unpublish_at: string | null };
  expect(saved).toMatchObject({ publish_at: null, unpublish_at: null });
});

test("a save over someone else's newer save is refused, and the editor reloads", async ({
  page,
}) => {
  const draft = await draftPage(page);
  await page.goto(`/admin/pages/${draft.id}?tab=settings`);
  const title = page.getByRole("textbox", { name: /^Title/ });
  await expect(title).toHaveValue(draft.title);

  // Someone else saves the page while this tab still holds the older version.
  const theirs = `E2E Their title ${runId()}`;
  const other = await apiCall(page, "PATCH", `/api/v1/admin/pages/${draft.id}`, { title: theirs });
  expect(other.status(), await other.text()).toBe(200);

  await title.fill(`E2E My title ${runId()}`);
  await page.getByRole("button", { name: "Save draft" }).click();
  const alert = page
    .getByRole("alert")
    .filter({ hasText: "This page was changed by someone else." });
  await expect(alert).toContainText("Someone else saved this page since you opened it.");
  await expectClean(page, "stale save alert");

  // Their title was kept: the API refused the stale save (409).
  const read = await apiCall(page, "GET", `/api/v1/admin/pages/${draft.id}`);
  expect(((await read.json()) as { title: string }).title).toBe(theirs);

  await alert.getByRole("button", { name: "Reload the page" }).click();
  await expect(alert).toBeHidden();
  await expect(page.getByRole("textbox", { name: /^Title/ })).toHaveValue(theirs);
  await expect(page.getByRole("heading", { level: 1, name: theirs })).toBeVisible();
  await expect(page.getByText("All changes saved")).toBeVisible();
});

test("a page that comes with the website keeps its address and can't be deleted", async ({
  page,
}) => {
  const legal = await seededLegalPage(page);
  const read = await apiCall(page, "GET", `/api/v1/admin/pages/${legal.id}`);
  expect(((await read.json()) as { is_required: boolean }).is_required).toBe(true);

  await page.goto(`/admin/pages/${legal.id}?tab=settings`);
  await expect(page.getByRole("textbox", { name: /^Web address/ })).toBeDisabled();
  await expect(
    page.getByText("This page comes with the website: it keeps its web address."),
  ).toBeVisible();
  // The kind is shown as text, not as a choice.
  await expect(page.getByRole("combobox", { name: /^Kind/ })).toHaveCount(0);
  const publishing = page.getByRole("complementary", { name: "Publishing" });
  await expect(publishing.getByRole("heading", { name: "Delete" })).toHaveCount(0);
  await expect(publishing.getByRole("heading", { name: "Archive" })).toHaveCount(0);

  // The API refuses both as well.
  const deleted = await apiCall(page, "DELETE", `/api/v1/admin/pages/${legal.id}`);
  expect(deleted.status()).toBe(409);
  const renamed = await apiCall(page, "PATCH", `/api/v1/admin/pages/${legal.id}`, {
    slug: `${legal.slug}-${runId()}`,
  });
  expect(renamed.status()).toBe(422);
});

test("a FAQs block whose last picked FAQ is deleted is hidden and says so", async ({ page }) => {
  const id = runId();
  const faq = await apiCall(page, "POST", "/api/v1/admin/faqs", {
    project_id: null,
    question: `E2E picked question ${id}?`,
    answer: "E2E answer.",
    is_visible: false,
  });
  expect(faq.status(), await faq.text()).toBe(201);
  const { id: faqId } = (await faq.json()) as { id: string };
  const draft = await draftPage(page);
  const blocks = await apiCall(page, "PUT", `/api/v1/admin/pages/${draft.id}/blocks`, {
    blocks: [{ type: "faq_list", data: { heading: null, faq_ids: [faqId] }, is_visible: true }],
  });
  expect(blocks.status(), await blocks.text()).toBe(200);
  const removed = await apiCall(page, "DELETE", `/api/v1/admin/faqs/${faqId}`);
  expect(removed.status()).toBe(204);

  // It no longer widens to every site-wide FAQ: the API hid it.
  const read = await apiCall(page, "GET", `/api/v1/admin/pages/${draft.id}`);
  const [block] = ((await read.json()) as { blocks: Array<{ is_visible: boolean }> }).blocks;
  expect(block?.is_visible).toBe(false);

  await page.goto(`/admin/pages/${draft.id}`);
  const row = page.getByRole("list", { name: "Blocks in page order" }).getByRole("listitem");
  await expect(row).toContainText("Hidden · nothing picked");
  await expect(row.getByRole("switch", { name: /Show on website/ })).toHaveAttribute(
    "aria-checked",
    "false",
  );
  await row.getByRole("button", { name: /^1\. FAQs/ }).click();
  await expect(
    page.getByText(/^Hidden, and no FAQs are picked\. .* it would list every site-wide FAQ/),
  ).toBeVisible();
  await expectClean(page, "hidden FAQs block note");
});
