/**
 * The blog's SEO (task 5.8, D-047): an article's title, canonical, description and `og:type`, and
 * the list's canonical.
 *
 * WHY the "serial" project: publishing a post makes it the newest one, which blog.spec.ts expects
 * to be its own post in the featured card; this runs after the main project has finished.
 */
import { expect, test } from "@playwright/test";
import { apiCall, CMS_STATE, runId } from "../lib/auth";
import { drainOutbox } from "../lib/catalogue";
import { cleanup } from "../lib/cleanup";
import { WEB_URL } from "../lib/env";

test.use({ storageState: CMS_STATE });

test("a blog article has its description, canonical and article card (task 5.8)", async ({
  page,
}) => {
  const id = runId();
  const made = await apiCall(page, "POST", "/api/v1/admin/posts", {
    title: `E2E SEO post ${id}`,
    excerpt: `E2E SEO excerpt ${id}.`,
    body: "Some *text* for the article.",
  });
  expect(made.status(), await made.text()).toBe(201);
  const post = (await made.json()) as { id: string; slug: string };
  const published = await apiCall(page, "POST", `/api/v1/admin/posts/${post.id}/publish`);
  expect(published.status(), await published.text()).toBe(200);
  let failed = true;
  try {
    await page.goto(`/blog/${post.slug}?utm_source=x`);
    await expect(page).toHaveTitle(new RegExp(`^E2E SEO post ${id} `));
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
      "href",
      `${WEB_URL}/blog/${post.slug}`,
    );
    await expect(page.locator('meta[name="description"]')).toHaveAttribute(
      "content",
      `E2E SEO excerpt ${id}.`,
    );
    await expect(page.locator('meta[property="og:type"]')).toHaveAttribute("content", "article");
    // A filtered list's canonical drops the filter; a later page keeps its own number (Google's
    // guidance for paginated lists).
    await page.goto("/blog?category=E2E%20none");
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", `${WEB_URL}/blog`);
    await page.goto("/blog?page=2&category=x");
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
      "href",
      `${WEB_URL}/blog?page=2`,
    );
    failed = false;
  } finally {
    await cleanup(failed, async () => {
      const off = await apiCall(page, "POST", `/api/v1/admin/posts/${post.id}/unpublish`);
      expect(off.status(), await off.text()).toBe(200);
      await drainOutbox(page);
    });
  }
});
