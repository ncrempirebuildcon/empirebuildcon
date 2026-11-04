/**
 * Page-builder pages on the public site (task 5.5a, D-045): a page built through the CMS API
 * with one block of most types, published and read at /<slug>; a legal page's DRAFT notice;
 * draft and unknown pages are 404; axe, the enforced CSP and 390 px.
 *
 * No real public lead submission: the lead-form block's send is answered by a mock, and the
 * request body is checked (project slug and source). The "home" and "contact" pages are
 * published in pages-home.serial.spec.ts, because other specs read "/" and "/contact".
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { cleanup } from "../lib/cleanup";
import { apiCall, CMS_STATE, runId } from "../lib/auth";
import { catalogueProject, drainOutbox } from "../lib/catalogue";
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

async function created201(page: Page, path: string, body: object): Promise<string> {
  const response = await apiCall(page, "POST", path, body);
  expect(response.status(), await response.text()).toBe(201);
  return ((await response.json()) as { id: string }).id;
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
  const faqId = await created201(page, "/api/v1/admin/faqs", {
    project_id: null,
    question: `E2E block question ${id}?`,
    answer: "E2E block answer.",
    is_visible: true,
  });
  const testimonialId = await created201(page, "/api/v1/admin/testimonials", {
    person_name: `E2E Buyer ${id}`,
    quote: "E2E quote, their words.",
    source: "E2E feedback form",
    consent_date: "2026-10-01",
    is_visible: true,
  });
  const offerId = await created201(page, "/api/v1/admin/offers", {
    title: `E2E offer ${id}`,
    body: "E2E offer body.",
    terms: "E2E terms line.",
    terms_url: "/terms",
    placement: "project",
    project_id: project.id,
    is_active: true,
  });
  let failed = true;
  try {
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
      { type: "faq_list", data: { heading: "Questions", faq_ids: [faqId] } },
      { type: "testimonials", data: { heading: "Buyers say", testimonial_ids: [testimonialId] } },
      { type: "offer_banner", data: { offer_id: offerId } },
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
    await expect(main.getByRole("heading", { name: "Homes" })).toBeVisible();
    await expect(main.getByRole("heading", { name: "Gallery" })).toBeVisible();
    await expect(main.getByText(`E2E block question ${id}?`)).toBeVisible();
    await expect(main.getByText(`E2E Buyer ${id}`)).toBeVisible();
    await expect(main.getByText(`E2E offer ${id}`)).toBeVisible();
    await expect(main.getByText("E2E terms line.")).toBeVisible();
    await expect(main.getByRole("link", { name: "Terms and conditions" })).toHaveAttribute(
      "href",
      "/terms",
    );
    // The map and lead-form blocks carry the project's full RERA block: number, QR and
    // up-rera.in (COMPLIANCE, D-045).
    for (const heading of ["Where it is", "Ask about it"]) {
      const section = main.locator("section", {
        has: visitor.getByRole("heading", { name: heading }),
      });
      const rera = section.getByTestId("rera-block");
      await expect(rera, heading).toBeVisible();
      await expect(rera.getByTestId("rera-number"), heading).toBeVisible();
      await expect(rera.getByRole("img", { name: /QR code/ }), heading).toBeVisible();
      await expect(
        rera.getByRole("link", { name: /Verify on up-rera\.in/ }),
        heading,
      ).toBeVisible();
    }

    expect(await seriousAxe(visitor)).toEqual([]);
    expect(csp).toEqual([]);

    await visitor.setViewportSize({ width: 390, height: 844 });
    await visitor.reload();
    const overflow = await visitor.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);

    // The lead-form block sends the project and its source; the answer is mocked (no real lead).
    const form = main.getByTestId("lead-form-enquiry");
    let sent: Record<string, unknown> | null = null;
    await visitor.route("**/api/v1/public/leads", async (route) => {
      sent = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ reference: "E2E-MOCK-1", message: "Thank you." }),
      });
    });
    await form.getByLabel("Your name").fill("E2E Block Lead");
    await form.getByLabel("Mobile number").fill("9876543210");
    await form.getByTestId("consent-required").check();
    await form.getByRole("button", { name: "Send" }).click();
    await expect(main.getByTestId("lead-success")).toContainText("E2E-MOCK-1");
    expect(sent).toMatchObject({ project_slug: project.slug, source: "project_form" });
    await visitorContext.close();
    failed = false;
  } finally {
    await cleanup(failed, async () => {
      // Leave nothing live for other specs or later runs, even when a check above failed.
      const cleanup = await Promise.all([
        apiCall(page, "PATCH", `/api/v1/admin/offers/${offerId}`, { is_active: false }),
        apiCall(page, "PATCH", `/api/v1/admin/faqs/${faqId}`, { is_visible: false }),
        apiCall(page, "PATCH", `/api/v1/admin/testimonials/${testimonialId}`, {
          is_visible: false,
        }),
      ]);
      for (const response of cleanup) expect(response.status(), await response.text()).toBe(200);
      await drainOutbox(page);
    });
  }
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

test("a site-visit form block with no project asks a plain question instead", async ({ page }) => {
  const created = await draftPage(page);
  await saveAndPublish(page, created.id, [
    { type: "lead_form", data: { heading: "Visit us", source: "site_visit" } },
  ]);
  await page.goto(`/${created.slug}`);
  // A site visit needs a project; a form that could never be sent is not shown.
  await expect(page.getByTestId("lead-form-enquiry")).toBeVisible();
  await expect(page.getByTestId("lead-form-visit")).toHaveCount(0);
});

test("/home is not a second copy of the home page", async ({ page }) => {
  const response = await page.goto("/home");
  expect(response?.status()).toBe(404);
});

test("draft and unknown pages are not found", async ({ page }) => {
  const draft = await draftPage(page);
  for (const path of [`/${draft.slug}`, "/e2e-no-such-page"]) {
    const response = await page.goto(path);
    expect(response?.status(), path).toBe(404);
    await expect(page.getByText("PAGE NOT FOUND")).toBeVisible();
  }
});
