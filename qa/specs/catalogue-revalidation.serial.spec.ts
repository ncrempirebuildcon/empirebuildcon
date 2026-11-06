/**
 * A CMS change reaches the cached project page through revalidation (task 5.3, D-041), within
 * seconds and with no manual drain (D-054: CMS writes deliver their events straight away).
 *
 * The negative control this test used to have (the cached page still shows the old text until
 * the outbox is drained) no longer holds by design. That pages are served from the data cache
 * is checked in apps/web/test/public-api-cache.test.ts (force-cache, our tags).
 * WHY still in the "serial" project: it needs its first drain to clear the publish events.
 */
import { expect, test } from "@playwright/test";
import { apiCall, CMS_STATE } from "../lib/auth";
import { catalogueProject, drainOutbox } from "../lib/catalogue";

test.use({ storageState: CMS_STATE });
test.describe.configure({ mode: "serial" });

test("a CMS change reaches the cached project page within seconds", async ({ browser, page }) => {
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
