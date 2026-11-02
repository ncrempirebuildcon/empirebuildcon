/**
 * A CMS change reaches the cached project page only after revalidation (task 5.3, D-041).
 *
 * WHY its own Playwright project ("serial", playwright.config.ts): the negative control (the
 * cached page still shows the old text before the outbox is drained) only holds when no other
 * spec drains the outbox at the same time. This project runs after the main one has finished.
 */
import { expect, test } from "@playwright/test";
import { apiCall, CMS_STATE } from "../lib/auth";
import { catalogueProject, drainOutbox } from "../lib/catalogue";

test.use({ storageState: CMS_STATE });
test.describe.configure({ mode: "serial" });

test("a CMS change reaches the cached project page after revalidation, not before", async ({
  browser,
  page,
}) => {
  const project = await catalogueProject(page);
  // Deliver the project's own publish events first, so only the change below is pending.
  await drainOutbox(page);

  const visitorContext = await browser.newContext();
  const visitor = await visitorContext.newPage();
  await visitor.goto(`/projects/${project.slug}`);
  await expect(visitor.getByText("Garden homes for the test suite")).toBeVisible();

  const tagline = `Revalidated ${Date.now()}`;
  const patched = await apiCall(page, "PATCH", `/api/v1/admin/projects/${project.id}`, {
    tagline,
  });
  expect(patched.status()).toBe(200);

  // Negative control: the page is served from the data cache, so before the outbox is drained
  // it still shows the old tagline (this fails if the page were not cached at all).
  await visitor.reload();
  await expect(visitor.getByText("Garden homes for the test suite")).toBeVisible();
  await expect(visitor.getByText(tagline)).toHaveCount(0);

  await drainOutbox(page);
  await expect
    .poll(
      async () => {
        await visitor.reload();
        return visitor.getByText(tagline).count();
      },
      { intervals: [500, 1000, 2000], timeout: 15_000 },
    )
    .toBe(1);
  await visitorContext.close();
});
