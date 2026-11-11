/**
 * The website assistant end to end (Phase 7, D-059): the widget (7.3) against the real
 * /api/v1/ai/chat (7.2) with the deterministic fake provider (AI_PROVIDER=fake in
 * playwright.config.ts), over the knowledge index the outbox keeps (7.1).
 *
 * WHY serial: it switches the site-wide `chat_widget` flag on, which other specs must not see
 * (chat-widget.spec.ts checks the launch state, flag off), and it drains the outbox.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { apiCall, CMS_STATE } from "../lib/auth";
import { type CatalogueProject, catalogueProject } from "../lib/catalogue";
import { API_URL, apiEnv } from "../lib/env";

test.use({ storageState: CMS_STATE });
test.describe.configure({ mode: "serial" });

let project: CatalogueProject;

/** Delivers the outbox until nothing due is left (as repeated sweeps would), up to 90 s. */
async function drainAll(page: Page): Promise<void> {
  const internalKey = apiEnv().INTERNAL_API_KEY ?? "dev-internal-key-32-chars-minimum-ok";
  const until = Date.now() + 90_000;
  while (Date.now() < until) {
    const res = await page.request.post(`${API_URL}/api/v1/internal/outbox/drain`, {
      headers: { "X-Internal-Key": internalKey },
    });
    if (res.status() === 429) {
      await page.waitForTimeout(1000); // another drain is running
      continue;
    }
    expect(res.status()).toBe(200);
    const { processed, failed } = (await res.json()) as { processed: number; failed: number };
    if (processed + failed === 0) return;
  }
  throw new Error("the outbox didn't empty within 90 s");
}

async function setChat(page: Page, enabled: boolean): Promise<void> {
  const res = await apiCall(page, "PATCH", "/api/v1/admin/flags/chat_widget", { enabled });
  expect(res.status(), await res.text()).toBe(200);
}

test.beforeAll(async ({ browser }) => {
  test.setTimeout(150_000);
  const admin = await (await browser.newContext({ storageState: CMS_STATE })).newPage();
  await admin.goto("/admin");
  project = await catalogueProject(admin);
  await setChat(admin, true);
  // The publish event queues `ai.reindex`, which only a full drain (the sweep) delivers, behind
  // whatever re-indexing earlier specs queued. Drain until nothing due is left, then check
  // once that the assistant finds the project (the chat limit is 12 per 10 minutes).
  // The request's own drain may still hold the publish event when the first drain runs, so
  // try up to three times (each try is one chat; the limit is 12 per 10 minutes).
  let found: string | undefined;
  for (let attempt = 0; attempt < 3 && found !== `/projects/${project.slug}`; attempt++) {
    await admin.waitForTimeout(2000);
    await drainAll(admin);
    const res = await apiCall(admin, "POST", "/api/v1/ai/chat", {
      message: `${project.name} central garden`,
      page: `/projects/${project.slug}`,
    });
    const body = (await res.json()) as { citations?: { url: string }[] };
    found = body.citations?.[0]?.url;
  }
  expect(found).toBe(`/projects/${project.slug}`);
});

test.afterAll(async ({ browser }) => {
  const admin = await (await browser.newContext({ storageState: CMS_STATE })).newPage();
  await admin.goto("/admin");
  await setChat(admin, false);
});

async function openChat(page: Page): Promise<void> {
  const launcher = page.getByRole("button", { name: /Ask about our projects/ });
  // The flag reaches the cached pages within seconds (D-054).
  await expect
    .poll(
      async () => {
        await page.reload();
        return launcher.count();
      },
      { intervals: [500, 1000, 2000], timeout: 20_000 },
    )
    .toBe(1);
  await launcher.click();
  await expect(page.getByRole("dialog", { name: /Ask about our projects/ })).toBeVisible();
}

async function ask(page: Page, question: string): Promise<void> {
  const box = page.getByRole("textbox", { name: /Ask a question/ });
  await box.fill(question);
  await box.press("Enter");
}

test("a visitor asks about a project and gets a cited answer with its card", async ({
  browser,
}) => {
  const visitor = await (await browser.newContext()).newPage();
  await visitor.goto(`/projects/${project.slug}`);
  await openChat(visitor);
  // The project's unique name keeps the fake (bag-of-words) search on it, whatever else
  // earlier runs left in the index.
  await ask(visitor, `Does ${project.name} have a central garden?`);

  const dialog = visitor.getByRole("dialog", { name: /Ask about our projects/ });
  // The citation links to the project's own page, and only there.
  // Twice: the [1] inside the answer and the sources list under it.
  const citations = dialog.getByRole("link", { name: new RegExp(`\\[1\\] ${project.name}`) });
  await expect(citations).toHaveCount(2, { timeout: 15_000 });
  for (const link of await citations.all()) {
    await expect(link).toHaveAttribute("href", `/projects/${project.slug}`);
  }
  // The card's RERA number comes from the project API, never from the answer (COMPLIANCE).
  await expect(dialog.getByText(project.rera)).toBeVisible();
  await expect(dialog.getByRole("link", { name: /Verify at up-rera\.in/ })).toBeVisible();

  const axe = await new AxeBuilder({ page: visitor }).include('[role="dialog"]').analyze();
  expect(axe.violations).toEqual([]);
});

test("a question nothing answers gets the fallback and the contact buttons", async ({
  browser,
}) => {
  const visitor = await (await browser.newContext()).newPage();
  await visitor.goto("/");
  await openChat(visitor);
  // Only short words: the fake embedder keeps none, so nothing can match.
  await ask(visitor, "is it ok to go?");
  const dialog = visitor.getByRole("dialog", { name: /Ask about our projects/ });
  // .first(): the message and its live-region announcement.
  await expect(dialog.getByText("I couldn't find that in our pages.").first()).toBeVisible({
    timeout: 15_000,
  });
  await expect(dialog.getByRole("link", { name: /Request a call back/ }).first()).toBeVisible();
});
