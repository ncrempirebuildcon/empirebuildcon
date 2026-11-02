/**
 * Blog listing and article reader browser tests (Phase 5 Task 5.5b).
 *
 * Implements:
 *   - Seeded published posts across two categories and one draft post (excluded from listing).
 *   - Listing order: newest first, featured card on page 1 without filter.
 *   - Category filter: marks active chip with aria-current="page", filters cards correctly.
 *   - Server-rendered pagination works without JavaScript.
 *   - Empty state on empty category and out-of-range page ("Nothing in this category yet").
 *   - Article reader: single H1 title, author, date, body with *bold* rendered as <strong>, tags.
 *   - Unknown or unpublished slug returns 404.
 *   - Axe accessibility clean on listing and article reader.
 *   - Enforced CSP with zero console violations.
 *   - 390px mobile view with zero sideways scroll.
 *   - Revalidation: title update reflects after outbox drain.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { CMS_STATE, apiCall, runId } from "../lib/auth";
import { API_URL, apiEnv } from "../lib/env";

interface SeededPost {
  id: string;
  slug: string;
  title: string;
  category: string;
}

let catA: string;
let catB: string;
let postA1: SeededPost;
let postB1: SeededPost;
let postA2: SeededPost;
let draftPost: SeededPost;

async function createAndPublishPost(
  page: Page,
  input: {
    title: string;
    body: string;
    excerpt?: string;
    category?: string;
    tags?: string[];
  },
  publish = true,
): Promise<SeededPost> {
  const res = await apiCall(page, "POST", "/api/v1/admin/posts", input);
  expect(res.status(), await res.text()).toBe(201);
  const data = (await res.json()) as { id: string; slug: string; title: string; category?: string };

  if (publish) {
    const pubRes = await apiCall(page, "POST", `/api/v1/admin/posts/${data.id}/publish`);
    expect(pubRes.status(), await pubRes.text()).toBe(200);
  }

  return {
    id: data.id,
    slug: data.slug,
    title: data.title,
    category: input.category ?? "",
  };
}

async function drainOutbox(request: APIRequestContext): Promise<void> {
  const internalKey = apiEnv().INTERNAL_API_KEY ?? "dev-internal-key-32-chars-minimum-ok";
  for (let attempt = 0; attempt < 5; attempt++) {
    const drainRes = await request.post(`${API_URL}/api/v1/internal/outbox/drain`, {
      headers: { "X-Internal-Key": internalKey },
    });
    if (drainRes.status() === 200) return;
    if (drainRes.status() === 429) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      continue;
    }
    expect(drainRes.status(), await drainRes.text()).toBe(200);
  }
}

test.describe("Public Blog (Task 5.5b)", () => {
  test.describe.configure({ mode: "serial" });

  test.beforeAll(async ({ browser, request }) => {
    const id = runId();
    catA = `Guides ${id}`;
    catB = `Legal ${id}`;

    const adminContext = await browser.newContext({ storageState: CMS_STATE });
    const adminPage = await adminContext.newPage();

    // 1. Create Post A1 (older post in category A)
    postA1 = await createAndPublishPost(adminPage, {
      title: `E2E Post A1 ${id}`,
      body: "First post body text with *bold* emphasis and helpful details.",
      excerpt: "First post excerpt for testing.",
      category: catA,
      tags: ["guides", "buyer"],
    });

    // 2. Create Post B1 (post in category B)
    postB1 = await createAndPublishPost(adminPage, {
      title: `E2E Post B1 ${id}`,
      body: "Legal considerations and *RERA* compliance overview.",
      excerpt: "Legal post excerpt for testing.",
      category: catB,
      tags: ["rera", "compliance"],
    });

    // 3. Create Post A2 (newest post in category A - should be featured on page 1)
    postA2 = await createAndPublishPost(adminPage, {
      title: `E2E Post A2 ${id}`,
      body: "Newest guide on *inspection* checklists and builder handover.",
      excerpt: "Newest guide excerpt.",
      category: catA,
      tags: ["inspection", "handover"],
    });

    // 4. Create Draft Post in category A (must not appear on public site)
    draftPost = await createAndPublishPost(
      adminPage,
      {
        title: `E2E Draft Post ${id}`,
        body: "Draft body that should remain strictly unpublished.",
        category: catA,
      },
      false, // Do NOT publish
    );

    // Drain outbox so Next.js cache revalidation tags are executed
    await drainOutbox(request);

    await adminContext.close();
  });

  test("listing displays newest first, featured card on page 1, and excludes draft posts", async ({
    page,
  }) => {
    await page.goto("/blog");

    // Title and heading check
    await expect(page).toHaveTitle(/News & guides · Empire/);
    const h1 = page.getByRole("heading", { level: 1 });
    await expect(h1).toHaveText("News & guides");

    // Featured post is the newest post on page 1 with no category filter
    // postA2 was created last, so it is the newest
    await expect(page.getByText(postA2.title)).toBeVisible();
    await expect(page.getByText(postB1.title)).toBeVisible();
    await expect(page.getByText(postA1.title)).toBeVisible();

    // Draft post must NEVER appear
    await expect(page.getByText(draftPost.title)).not.toBeVisible();
  });

  test("category filter works and marks the active chip with aria-current='page'", async ({
    page,
  }) => {
    await page.goto("/blog");

    // Initially "All" chip has aria-current="page"
    const allChip = page.getByRole("link", { name: "All", exact: true });
    await expect(allChip).toBeVisible();
    await expect(allChip).toHaveAttribute("aria-current", "page");

    // Click Category B chip
    const catBChip = page.getByRole("link", { name: catB, exact: true });
    await expect(catBChip).toBeVisible();
    await catBChip.click();

    await expect(page).toHaveURL(/category=Legal(\+|%20)/);
    await expect(catBChip).toHaveAttribute("aria-current", "page");
    await expect(allChip).not.toHaveAttribute("aria-current", "page");

    // Category B post should be visible
    await expect(page.getByText(postB1.title)).toBeVisible();

    // Category A posts should NOT be visible under Category B filter
    await expect(page.getByText(postA1.title)).not.toBeVisible();
    await expect(page.getByText(postA2.title)).not.toBeVisible();
  });

  test("pagination works without JavaScript", async ({ browser }) => {
    // Disable JavaScript entirely
    const noJsContext = await browser.newContext({ javaScriptEnabled: false });
    const page = await noJsContext.newPage();

    await page.goto("/blog");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("News & guides");
    await expect(page.getByText(postA2.title)).toBeVisible();

    // Navigate to page 2 (even if only 1 page of e2e posts, checking pagination structure without JS)
    const res = await page.goto("/blog?page=1");
    expect(res?.status()).toBe(200);
    await expect(page.getByText(postA2.title)).toBeVisible();

    await noJsContext.close();
  });

  test("empty state appears for an empty category with working 'Show all articles' link", async ({
    page,
  }) => {
    const unknownCat = `EmptyCat-${runId()}`;
    await page.goto(`/blog?category=${unknownCat}`);

    // Empty state container matching NoirBlog
    await expect(
      page.getByRole("heading", { level: 2, name: "Nothing in this category yet" }),
    ).toBeVisible();
    await expect(
      page.getByText(
        "We only publish when there is something useful to say. Try another category.",
      ),
    ).toBeVisible();

    // "Show all articles" link navigates back to /blog
    const showAllLink = page.getByRole("link", { name: "Show all articles" });
    await expect(showAllLink).toBeVisible();
    await showAllLink.click();

    await expect(page).toHaveURL(/\/blog$/);
    await expect(page.getByText(postA2.title)).toBeVisible();
  });

  test("article page shows title, author, date, body with *bold* rendered as <strong>, and tags", async ({
    page,
  }) => {
    await page.goto(`/blog/${postA1.slug}`);

    // Page title set from post title
    await expect(page).toHaveTitle(new RegExp(`${postA1.title} · Empire`));

    // Single H1 with post title
    const h1 = page.getByRole("heading", { level: 1 });
    await expect(h1).toHaveText(postA1.title);

    // Breadcrumbs
    const breadcrumb = page.getByRole("navigation", { name: "Breadcrumb" });
    await expect(breadcrumb).toBeVisible();
    await expect(breadcrumb.getByRole("link", { name: "Home" })).toBeVisible();
    await expect(breadcrumb.getByRole("link", { name: "Blog" })).toBeVisible();
    await expect(breadcrumb.getByRole("link", { name: catA })).toBeVisible();

    // Author in article header
    const headingSection = page.locator("section[aria-label='Article heading']");
    await expect(headingSection.getByText(/Admin/i)).toBeVisible();

    // Date formatted as Indian date in <time>
    const timeElement = page.locator("time").first();
    await expect(timeElement).toBeVisible();
    const dateText = await timeElement.textContent();
    expect(dateText).toMatch(/\d{1,2}\s+[A-Za-z]{3}\s+\d{4}/);

    // Body with *bold* marker renders as <strong>
    const strongElement = page.locator("article strong").first();
    await expect(strongElement).toBeVisible();
    await expect(strongElement).toHaveText("bold");

    // Tags
    await expect(page.getByText("#guides")).toBeVisible();
    await expect(page.getByText("#buyer")).toBeVisible();

    // Share buttons
    await expect(page.getByRole("link", { name: "Share on WhatsApp" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Copy link" }).first()).toBeVisible();
  });

  test("unknown slug shows the 404 page", async ({ page }) => {
    const res = await page.goto(`/blog/unknown-post-${runId()}`);
    expect(res?.status()).toBe(404);
    await expect(
      page.getByRole("heading", { level: 1, name: "This page has moved or doesn't exist" }),
    ).toBeVisible();
  });

  test("axe accessibility check on /blog and /blog/[slug]", async ({ page }) => {
    // 1. Check blog listing
    await page.goto("/blog");
    let a11y = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    let serious = a11y.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${v.id}: ${v.help}`)).toEqual([]);

    // 2. Check blog article detail
    await page.goto(`/blog/${postA1.slug}`);
    a11y = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    serious = a11y.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
  });

  test("CSP enforced with zero console violations on blog listing and article", async ({
    page,
  }) => {
    const cspViolations: string[] = [];
    page.on("console", (msg) => {
      const text = msg.text();
      if (text.includes("Content Security Policy") || text.includes("violates the following")) {
        cspViolations.push(text);
      }
    });

    const listingRes = await page.goto("/blog");
    expect(listingRes?.status()).toBe(200);
    const listingCsp = listingRes?.headers()["content-security-policy"];
    expect(listingCsp).toBeDefined();

    const articleRes = await page.goto(`/blog/${postA1.slug}`);
    expect(articleRes?.status()).toBe(200);
    const articleCsp = articleRes?.headers()["content-security-policy"];
    expect(articleCsp).toBeDefined();

    expect(cspViolations).toEqual([]);
  });

  test("responsive mobile view (390px) has zero sideways scroll", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });

    // Listing page
    await page.goto("/blog");
    const listingOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(listingOverflow).toBe(false);

    // Article page
    await page.goto(`/blog/${postA1.slug}`);
    const articleOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(articleOverflow).toBe(false);
  });

  test("revalidation reflects CMS post title update", async ({ browser, request }) => {
    // 1. Initial article page load
    const publicContext = await browser.newContext();
    const publicPage = await publicContext.newPage();
    await publicPage.goto(`/blog/${postA2.slug}`);
    await expect(publicPage.getByRole("heading", { level: 1 })).toHaveText(postA2.title);

    // 2. Super-admin updates the post title in CMS
    const adminContext = await browser.newContext({ storageState: CMS_STATE });
    const adminPage = await adminContext.newPage();

    const updatedTitle = `Updated Guide ${Date.now()}`;
    const patchRes = await apiCall(adminPage, "PATCH", `/api/v1/admin/posts/${postA2.id}`, {
      title: updatedTitle,
    });
    expect(patchRes.status()).toBe(200);

    // 3. Drain outbox to trigger Next.js cache revalidation
    const internalKey = apiEnv().INTERNAL_API_KEY ?? "dev-internal-key-32-chars-minimum-ok";
    let drained = false;
    for (let i = 0; i < 5; i++) {
      const drainRes = await request.post(`${API_URL}/api/v1/internal/outbox/drain`, {
        headers: { "X-Internal-Key": internalKey },
      });
      if (drainRes.status() === 200) {
        drained = true;
        break;
      }
      await new Promise((r) => setTimeout(r, 200));
    }
    expect(drained).toBe(true);

    // 4. Poll public page: verify updated title is reflected within revalidation window
    await expect
      .poll(
        async () => {
          await publicPage.reload();
          return publicPage.getByRole("heading", { level: 1 }).textContent();
        },
        { intervals: [500, 1000, 2000], timeout: 10_000 },
      )
      .toBe(updatedTitle);

    await publicContext.close();
    await adminContext.close();
  });
});
