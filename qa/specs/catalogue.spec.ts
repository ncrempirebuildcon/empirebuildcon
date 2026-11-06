/**
 * Public catalogue journeys (task 5.3): the projects list with filters in the URL (also without
 * JavaScript), the project page with its RERA block and honest prices, the property page, city
 * pages, the map on tap, 404s for hidden projects, axe, the enforced CSP and 390 px. The
 * revalidation journey is in catalogue-revalidation.serial.spec.ts (it needs no parallel drains).
 *
 * Data: projects are made through the CMS API as the signed-in super-admin (no extra sign-ins),
 * named "E2E Catalogue …" (qa/lib/catalogue.ts).
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { apiCall, CMS_STATE } from "../lib/auth";
import { catalogueProject, drainOutbox } from "../lib/catalogue";

test.use({ storageState: CMS_STATE });

/** Collects CSP violations reported in the console (the suite runs with CSP_ENFORCE=true). */
function watchCsp(page: Page): string[] {
  const violations: string[] = [];
  page.on("console", (msg) => {
    const text = msg.text();
    if (text.includes("Content Security Policy") || text.includes("violates the following")) {
      violations.push(text);
    }
  });
  return violations;
}

async function seriousAxe(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join(", ")})`);
}

async function noSidewaysScroll(page: Page): Promise<void> {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, "no sideways scroll").toBeLessThanOrEqual(0);
}

test("the projects list finds a project by search and shows its RERA number and price note", async ({
  page,
}) => {
  const project = await catalogueProject(page);
  const csp = watchCsp(page);

  await page.goto("/projects");
  await expect(
    page.getByRole("heading", { level: 1, name: "Projects in Uttar Pradesh" }),
  ).toBeVisible();
  await page.getByRole("searchbox", { name: "Search" }).fill(project.name);
  await page.getByRole("button", { name: "Show results" }).click();
  await expect(page).toHaveURL(
    new RegExp(`/projects\\?q=${encodeURIComponent(project.name).replace(/%20/g, "\\+")}`),
  );

  const card = page.getByTestId("project-card").filter({ hasText: project.name });
  await expect(card).toHaveCount(1);
  await expect(card.getByTestId("rera-line")).toContainText(project.rera);
  await expect(card.getByTestId("price")).toHaveText("₹ 78 L – ₹ 1.25 Cr");
  await expect(card.getByTestId("price-note")).toContainText(
    "excludes GST, stamp duty and registration",
  );
  await expect(card.getByText("Artist's impression")).toBeVisible();
  await expect(card.getByRole("link", { name: /^Verify on up-rera\.in for / })).toHaveAttribute(
    "href",
    "https://www.up-rera.in",
  );
  expect(await seriousAxe(page)).toEqual([]);
  expect(csp).toEqual([]);

  // A filter that excludes it (budget above ₹ 1.5 Cr) shows the honest empty state.
  await page.goto(`/projects?q=${encodeURIComponent(project.name)}&budget=above-1.5cr`);
  await expect(
    page.getByRole("heading", { name: "No projects match these filters" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Clear filters" })).toHaveAttribute(
    "href",
    "/projects",
  );
});

test("filters work without JavaScript", async ({ browser, page }) => {
  const project = await catalogueProject(page);
  const context = await browser.newContext({ javaScriptEnabled: false });
  const visitor = await context.newPage();
  await visitor.goto("/projects");
  await visitor.getByRole("searchbox", { name: "Search" }).fill(project.name);
  await visitor.getByLabel("Status").selectOption("ongoing");
  await visitor.getByRole("button", { name: "Show results" }).click();
  await expect(visitor).toHaveURL(/status=ongoing/);
  await expect(visitor.getByTestId("project-card").filter({ hasText: project.name })).toHaveCount(
    1,
  );

  // "Ready to move" excludes this under-construction project.
  await visitor.getByLabel("Status").selectOption("completed");
  await visitor.getByRole("button", { name: "Show results" }).click();
  await expect(visitor.getByTestId("project-card").filter({ hasText: project.name })).toHaveCount(
    0,
  );

  // The map button needs JavaScript, so it is not offered; the directions link is.
  await visitor.goto(`/projects/${project.slug}`);
  await expect(visitor.getByRole("button", { name: "Show map" })).toHaveCount(0);
  await expect(visitor.getByRole("link", { name: /Get directions/ })).toHaveAttribute(
    "href",
    /^https:\/\/www\.google\.com\/maps\/dir\/\?api=1&destination=28\.4744\d*,77\.504\d*$/,
  );
  await context.close();
});

test("the project page shows the RERA block, carpet area first and the price note", async ({
  page,
}) => {
  const project = await catalogueProject(page);
  const csp = watchCsp(page);
  const res = await page.goto(`/projects/${project.slug}`);
  expect(res?.status()).toBe(200);

  await expect(page.getByRole("heading", { level: 1, name: project.name })).toBeVisible();
  const rera = page.getByTestId("rera-block").first();
  await expect(rera.getByTestId("rera-number")).toHaveText(project.rera);
  await expect(
    rera.getByRole("img", { name: `UP-RERA QR code for ${project.name}` }),
  ).toBeVisible();
  await expect(rera.getByRole("link", { name: /Verify on up-rera\.in/ })).toHaveAttribute(
    "href",
    "https://www.up-rera.in",
  );
  const facts = page.getByTestId("key-facts");
  await expect(facts.getByTestId("price")).toHaveText("₹ 78 L – ₹ 1.25 Cr");
  await expect(facts.getByTestId("price-note")).toContainText("stamp duty");
  await expect(facts).toContainText("June 2029");

  // Carpet area first, in sq ft then sq m, with the basis.
  const rows = page.getByTestId("configuration-row");
  await expect(rows).toHaveCount(2);
  await expect(rows.first().getByTestId("area")).toHaveText("720 sq ft · 66.9 sq m (carpet)");
  await expect(rows.nth(1)).toContainText("Sold out");

  // Floor plans of the home types are on the project page too, linking to their pages.
  const plans = page.getByTestId("floor-plans");
  await expect(plans.getByRole("img", { name: `${project.name} 2 BHK floor plan` })).toBeVisible();
  await expect(plans.getByRole("link", { name: "2 BHK (test)" })).toHaveAttribute(
    "href",
    `/projects/${project.slug}/${project.configSlugs[0]}`,
  );

  // Description is formatted text, never HTML.
  await expect(page.locator("#overview strong", { hasText: "sample" })).toBeVisible();
  expect(await seriousAxe(page)).toEqual([]);
  expect(csp).toEqual([]);

  // The configuration links to its property page, which repeats the RERA block.
  await rows.first().getByRole("link").click();
  await expect(page).toHaveURL(`/projects/${project.slug}/${project.configSlugs[0]}`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("2 BHK (test)");
  await expect(page.getByTestId("rera-block").getByTestId("rera-number")).toHaveText(project.rera);
  await expect(page.getByTestId("key-facts").getByTestId("area")).toHaveText(
    "720 sq ft · 66.9 sq m (carpet)",
  );
  await expect(page.getByTestId("lead-form-enquiry")).toBeVisible();
  await expect(page.getByTestId("lead-form-enquiry")).not.toContainText("(Required) (Required)");
  expect(await seriousAxe(page)).toEqual([]);

  // The sold-out home says so and takes no enquiries.
  await page.goto(`/projects/${project.slug}/${project.configSlugs[1]}`);
  await expect(page.getByRole("heading", { name: "Every 3 BHK (test) is booked" })).toBeVisible();
  // No enquiry panel at all: neither the form nor its pre-hydration fallback.
  await expect(page.getByTestId("lead-form-enquiry")).toHaveCount(0);
  await expect(page.getByTestId("lead-fallback")).toHaveCount(0);
  expect(csp).toEqual([]);
});

test("price on request on the project hides every number, its homes' too", async ({ page }) => {
  const project = await catalogueProject(page, { priceOnRequest: true });
  await page.goto(`/projects/${project.slug}`);
  const main = page.locator("#main-content");
  await expect(page.getByTestId("key-facts").getByTestId("price")).toHaveText("Price on request");
  await expect(main).not.toContainText("₹");
  await page.goto(`/projects/${project.slug}/${project.configSlugs[0]}`);
  await expect(page.getByTestId("key-facts").getByTestId("price")).toHaveText("Price on request");
  await expect(page.locator("#main-content")).not.toContainText("₹");
});

test("off-market, draft and unknown projects are not found", async ({ page }) => {
  const offMarket = await catalogueProject(page);
  const patched = await apiCall(page, "PATCH", `/api/v1/admin/projects/${offMarket.id}`, {
    sales_status: "off_market",
  });
  expect(patched.status()).toBe(200);
  const draft = await catalogueProject(page, { publish: false });

  for (const path of [
    `/projects/${offMarket.slug}`,
    `/projects/${draft.slug}`,
    `/projects/${draft.slug}/${draft.configSlugs[0]}`,
    "/projects/no-such-project",
    "/cities/no-such-city",
  ]) {
    const res = await page.goto(path);
    expect(res?.status(), path).toBe(404);
    await expect(page.getByText("PAGE NOT FOUND", { exact: true })).toBeVisible();
  }
});

test("a city page lists the city's projects", async ({ page }) => {
  const project = await catalogueProject(page);
  await page.goto(`/projects/${project.slug}`);
  await page
    .getByRole("navigation", { name: "Breadcrumb" })
    .getByRole("link", { name: "Sample City" })
    .click();
  await expect(page).toHaveURL("/cities/sample-city");
  await expect(
    page.getByRole("heading", { level: 1, name: "Projects in Sample City" }),
  ).toBeVisible();
  // The city is fixed by the address, so the form offers no city choice.
  await expect(page.getByLabel("City")).toHaveCount(0);
  await page.goto(`/cities/sample-city?q=${encodeURIComponent(project.name)}`);
  await expect(page.getByTestId("project-card").filter({ hasText: project.name })).toHaveCount(1);
});

test("the map loads only on tap, with the pin's pop-up and OpenStreetMap attribution", async ({
  page,
}) => {
  const project = await catalogueProject(page);
  const tileRequests: string[] = [];
  // WHY stub: the suite must not load real tiles from OpenStreetMap (its tile policy).
  await page.route("https://tile.openstreetmap.org/**", async (route) => {
    tileRequests.push(route.request().url());
    await route.fulfill({
      contentType: "image/png",
      body: Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
        "base64",
      ),
    });
  });
  const csp = watchCsp(page);
  await page.goto(`/projects/${project.slug}`);
  await page.locator("#location").scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", { name: "Show map" })).toBeVisible();
  expect(tileRequests, "no tiles before the tap").toEqual([]);

  await page.getByRole("button", { name: "Show map" }).click();
  const map = page.getByRole("region", { name: `Map showing ${project.name}` });
  await expect(map).toBeVisible();
  await expect(map.locator(".leaflet-popup-content")).toContainText(project.name);
  await expect(map.locator(".leaflet-popup-content")).toContainText(`UP-RERA ${project.rera}`);
  await expect(map.getByRole("link", { name: "OpenStreetMap" })).toBeVisible();
  // Zoom buttons are 44 px touch targets, not Leaflet's 30 px.
  const zoomIn = map.getByRole("button", { name: "Zoom in" });
  const box = await zoomIn.boundingBox();
  expect(box?.width).toBeGreaterThanOrEqual(44);
  expect(box?.height).toBeGreaterThanOrEqual(44);
  await expect.poll(() => tileRequests.length).toBeGreaterThan(0);
  expect(csp).toEqual([]);
});

test("the catalogue works at 390 px without sideways scroll", async ({ page }) => {
  const project = await catalogueProject(page);
  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of [
    "/projects",
    "/properties",
    `/projects/${project.slug}`,
    `/projects/${project.slug}/${project.configSlugs[0]}`,
    "/cities/sample-city",
  ]) {
    const res = await page.goto(path);
    expect(res?.status(), path).toBe(200);
    await noSidewaysScroll(page);
    expect(await seriousAxe(page), path).toEqual([]);
  }
});

test("the properties list shows homes with carpet area first and the project's RERA number", async ({
  page,
}) => {
  const project = await catalogueProject(page);
  // The lists are cached by tag; a new project shows once the outbox has told the site.
  await drainOutbox(page);
  const path = "/properties?city=sample-city&bhk=2&budget=75l-1.5cr";
  await page.goto(path);
  // WHY from the last page back: earlier runs leave their test homes in the sample city, and
  // the newest home sorts last (the list orders by the configuration's order, then its id).
  const total = Number(
    ((await page.getByRole("status").first().textContent()) ?? "0").split(" ")[0],
  );
  const pages = Math.max(1, Math.ceil(total / 12));
  const card = page.getByTestId("property-card").filter({ hasText: project.name });
  for (let p = pages; p >= 1 && (await card.count()) === 0; p -= 1) {
    await page.goto(`${path}&page=${p}`);
  }
  await expect(card).toHaveCount(1);
  await expect(card.getByTestId("area")).toHaveText("720 sq ft · 66.9 sq m (carpet)");
  await expect(card.getByTestId("rera-line")).toContainText(project.rera);
  expect(await seriousAxe(page)).toEqual([]);
});
