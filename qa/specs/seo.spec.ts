/**
 * SEO on the public site (task 5.6, D-047): titles, descriptions, canonical URLs and share cards;
 * JSON-LD that parses, carries the CSP nonce and says only what the page says; CMS redirects
 * answered by the website (308/301, query kept) and counted.
 *
 * No public submissions and no sign-ins. The web server keeps redirects for one second in this
 * suite (REDIRECT_CACHE_SECONDS, playwright.config.ts), so a new redirect works at once.
 */
import { expect, type Page, test } from "@playwright/test";
import { apiCall, CMS_STATE, runId } from "../lib/auth";
import { catalogueProject } from "../lib/catalogue";
import { draftPage } from "../lib/content";
import { WEB_URL } from "../lib/env";

test.use({ storageState: CMS_STATE });

async function jsonLd(page: Page): Promise<Record<string, unknown>[]> {
  const blocks = await page
    .locator('script[type="application/ld+json"]')
    .evaluateAll((nodes) =>
      nodes.map((n) => ({ text: n.textContent ?? "", nonce: (n as HTMLScriptElement).nonce })),
    );
  for (const block of blocks) expect(block.nonce, "every JSON-LD block has the nonce").not.toBe("");
  return blocks.map((b) => JSON.parse(b.text) as Record<string, unknown>);
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

test("a project page has its title, canonical, share card and listing data", async ({
  page,
  browser,
}) => {
  const project = await catalogueProject(page);
  const visitorContext = await browser.newContext();
  const visitor = await visitorContext.newPage();
  const csp = watchCsp(visitor);
  await visitor.goto(`/projects/${project.slug}?utm_source=e2e`);

  await expect(visitor).toHaveTitle(new RegExp(`^${project.name} `));
  // WHY the whole document: Next.js streams metadata for browsers (it may land in <body>);
  // crawlers get it in <head>, checked in the next test.
  const head = visitor.locator("html");
  await expect(head.locator('link[rel="canonical"]')).toHaveAttribute(
    "href",
    `${WEB_URL}/projects/${project.slug}`,
  );
  await expect(head.locator('meta[name="description"]')).toHaveAttribute(
    "content",
    "Garden homes for the test suite",
  );
  await expect(head.locator('meta[property="og:url"]')).toHaveAttribute(
    "content",
    `${WEB_URL}/projects/${project.slug}`,
  );
  await expect(head.locator('meta[property="og:image"]').first()).toHaveAttribute(
    "content",
    /^https?:\/\//,
  );
  await expect(head.locator('meta[name="twitter:card"]')).toHaveAttribute(
    "content",
    "summary_large_image",
  );
  // Nothing is indexed before go-live (Phase 9 gate).
  await expect(head.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);

  const ld = await jsonLd(visitor);
  const listing = ld.find((d) => d["@type"] === "RealEstateListing");
  expect(listing, JSON.stringify(ld)).toBeTruthy();
  expect(listing?.identifier).toMatchObject({ propertyID: "UP-RERA", value: project.rera });
  expect(listing?.url).toBe(`${WEB_URL}/projects/${project.slug}`);
  const crumbs = ld.find((d) => d["@type"] === "BreadcrumbList") as {
    itemListElement: { name: string }[];
  };
  expect(crumbs.itemListElement.map((i) => i.name)).toEqual([
    "Home",
    "Projects",
    expect.any(String),
    project.name,
  ]);
  expect(csp).toEqual([]);
  await visitorContext.close();
});

// WHY a link-preview bot: Next.js puts metadata in <head> for crawlers that don't run
// JavaScript (WhatsApp, Facebook, Bing…); Googlebot runs it and reads the streamed tags.
test("a link-preview crawler gets the metadata in <head>", async ({ browser, page }) => {
  const project = await catalogueProject(page);
  const crawler = await browser.newContext({ userAgent: "WhatsApp/2.23.20.0 A" });
  const response = await crawler.request.get(`${WEB_URL}/projects/${project.slug}`);
  const html = await response.text();
  const headHtml = html.slice(0, html.indexOf("</head>"));
  expect(headHtml).toContain(`<link rel="canonical" href="${WEB_URL}/projects/${project.slug}"`);
  expect(headHtml).toContain('property="og:title"');
  await crawler.close();
});

test("price on request leaves the price out of the listing data", async ({ page }) => {
  const project = await catalogueProject(page, { priceOnRequest: true });
  await page.goto(`/projects/${project.slug}`);
  const listing = (await jsonLd(page)).find((d) => d["@type"] === "RealEstateListing");
  expect(listing).toBeTruthy();
  expect(listing).not.toHaveProperty("offers");
  await page.goto(`/projects/${project.slug}/${project.configSlugs[0]}`);
  const home = (await jsonLd(page)).find((d) => d["@type"] === "RealEstateListing");
  expect(home).toBeTruthy();
  expect(home).not.toHaveProperty("offers");
});

test("a filtered list's canonical is the list itself", async ({ page }) => {
  await page.goto("/projects?city=sample-city&sort=price_asc");
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    "href",
    `${WEB_URL}/projects`,
  );
});

test("a page's SEO fields from the CMS reach its head", async ({ page }) => {
  const id = runId();
  const created = await draftPage(page);
  const patched = await apiCall(page, "PATCH", `/api/v1/admin/pages/${created.id}`, {
    seo: { title: `E2E SEO title ${id}`, description: `E2E SEO description ${id}.` },
  });
  expect(patched.status(), await patched.text()).toBe(200);
  await apiCall(page, "PUT", `/api/v1/admin/pages/${created.id}/blocks`, {
    blocks: [{ type: "rich_text", data: { body: "E2E text" } }],
  });
  const published = await apiCall(page, "POST", `/api/v1/admin/pages/${created.id}/publish`);
  expect(published.status(), await published.text()).toBe(200);
  await page.goto(`/${created.slug}`);
  await expect(page).toHaveTitle(new RegExp(`^E2E SEO title ${id} `));
  await expect(page.locator('meta[name="description"]')).toHaveAttribute(
    "content",
    `E2E SEO description ${id}.`,
  );
  await expect(page.locator('meta[property="og:title"]')).toHaveAttribute(
    "content",
    `E2E SEO title ${id}`,
  );
});

test("the home page carries the organisation's structured data", async ({ page }) => {
  await page.goto("/");
  const org = (await jsonLd(page)).find((d) => d["@type"] === "Organization");
  expect(org?.url).toBe(`${WEB_URL}/`);
  expect(JSON.stringify(org)).not.toMatch(/\[[^\]]*\]/); // no [placeholders]
});

test("a CMS redirect is answered by the website and counted", async ({ page, browser }) => {
  const id = runId();
  const from = `/e2e-old-${id}`;
  const made = await apiCall(page, "POST", "/api/v1/admin/redirects", {
    from_path: from,
    to_path: "/projects",
  });
  expect(made.status(), await made.text()).toBe(201);
  const { id: redirectId } = (await made.json()) as { id: string };

  // A fresh request context: no cookies, no redirects followed.
  const visitor = await browser.newContext({ baseURL: WEB_URL });
  let response = await visitor.request.get(`${from}/?utm_source=e2e`, { maxRedirects: 0 });
  await expect
    .poll(
      async () => {
        response = await visitor.request.get(`${from}/?utm_source=e2e`, { maxRedirects: 0 });
        return response.status();
      },
      { timeout: 10_000 },
    )
    .toBe(308);
  expect(response.headers()["location"]).toMatch(/\/projects\?utm_source=e2e$/);

  // The visit was counted (sent after the answer, so allow a moment).
  await expect
    .poll(
      async () => {
        const list = await apiCall(page, "GET", "/api/v1/admin/redirects?per_page=100&q=e2e-old");
        const { items } = (await list.json()) as { items: { id: string; hits: number }[] };
        return items.find((r) => r.id === redirectId)?.hits ?? 0;
      },
      { timeout: 10_000 },
    )
    .toBeGreaterThanOrEqual(1);

  // Switched off, the old address is a 404 again.
  const off = await apiCall(page, "PATCH", `/api/v1/admin/redirects/${redirectId}`, {
    is_active: false,
  });
  expect(off.status(), await off.text()).toBe(200);
  await expect
    .poll(async () => (await visitor.request.get(from, { maxRedirects: 0 })).status(), {
      timeout: 10_000,
    })
    .toBe(404);
  await visitor.close();
});
