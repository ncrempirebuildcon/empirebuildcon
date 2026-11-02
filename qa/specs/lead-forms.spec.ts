/**
 * Public lead forms (task 5.4, D-043): an enquiry from a project page, a site visit from the
 * contact page and a gated brochure, each checked through the staff API (consent text and
 * version, marketing only when ticked, attribution, path-only page address); the error states
 * with mocked answers; axe, the enforced CSP and 390 px.
 *
 * Budget: exactly 3 real public submissions per run (intake allows 5 per 10 minutes per network;
 * leads.spec.ts makes 1). The error states use mocked answers and submit nothing.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { apiCall, CMS_STATE } from "../lib/auth";
import { attachBrochure, catalogueProject } from "../lib/catalogue";
import { currentConsent, testMobile } from "../lib/leads";

test.use({ storageState: CMS_STATE });

interface LeadDetail {
  reference: string;
  name: string;
  source: string;
  page_url: string | null;
  utm: { source: string | null; campaign: string | null };
  click_ids: { gclid: string | null };
  consent: { consent_text_id: string; text_version: number };
  marketing_consent: { consent_text_id: string } | null;
}

async function leadByReference(page: Page, reference: string): Promise<LeadDetail> {
  const list = await apiCall(page, "GET", `/api/v1/admin/leads?q=${encodeURIComponent(reference)}`);
  expect(list.status()).toBe(200);
  const { items } = (await list.json()) as { items: { id: string; reference: string }[] };
  const found = items.find((l) => l.reference === reference);
  expect(found, `lead ${reference}`).toBeTruthy();
  const detail = await apiCall(page, "GET", `/api/v1/admin/leads/${found?.id}`);
  expect(detail.status()).toBe(200);
  return (await detail.json()) as LeadDetail;
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

async function seriousAxe(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.help}`);
}

test("an enquiry from a project page records the consent version and attribution", async ({
  page,
  browser,
}) => {
  const project = await catalogueProject(page);
  const consent = await currentConsent(page);
  const visitorContext = await browser.newContext();
  const visitor = await visitorContext.newPage();
  const csp = watchCsp(visitor);

  // The visitor lands from an ad, then reads the project page.
  await visitor.goto(`/projects/${project.slug}?utm_source=e2e&utm_campaign=forms&gclid=E2E-CLICK`);
  const form = visitor.getByTestId("lead-form-enquiry");
  await expect(form).toBeVisible();
  const required = form.getByTestId("consent-required");
  const marketing = form.getByTestId("consent-marketing");
  // COMPLIANCE: two separate boxes, neither ticked.
  await expect(required).not.toBeChecked();
  await expect(marketing).not.toBeChecked();
  await expect(form).toContainText(consent.checkbox_label);
  expect(await seriousAxe(visitor)).toEqual([]);

  const name = `E2E Form ${Date.now()}`;
  await form.getByLabel("Your name").fill(name);
  await form.getByLabel("Mobile number").fill(testMobile());

  // Without the required box nothing is sent, and the form says why.
  await form.getByRole("button", { name: "Request a call back" }).click();
  await expect(form.getByTestId("lead-message")).toContainText("Please tick the required box");

  await required.check();
  await form.getByRole("button", { name: "Request a call back" }).click();
  const success = visitor.getByTestId("lead-success");
  await expect(success).toContainText("Your reference:");
  const reference = (await success.locator(".tabular-nums").textContent())?.trim() ?? "";
  expect(reference).toMatch(/^EMP-/);
  expect(csp).toEqual([]);

  const lead = await leadByReference(page, reference);
  expect(lead.name).toBe(name);
  expect(lead.source).toBe("project_form");
  expect(lead.consent.consent_text_id).toBe(consent.id);
  expect(lead.consent.text_version).toBe(consent.version);
  expect(lead.marketing_consent).toBeNull();
  expect(lead.page_url).toBe(`/projects/${project.slug}`);
  expect(lead.utm.source).toBe("e2e");
  expect(lead.utm.campaign).toBe("forms");
  expect(lead.click_ids.gclid).toBe("E2E-CLICK");
  await visitorContext.close();
});

test("a site visit from the contact page records marketing consent when ticked", async ({
  page,
  browser,
}) => {
  const project = await catalogueProject(page);
  const visitorContext = await browser.newContext();
  const visitor = await visitorContext.newPage();
  await visitor.goto(`/contact?project=${project.slug}`);
  const form = visitor.getByTestId("lead-form-visit");
  await expect(form.getByLabel("Project")).toHaveValue(project.slug);
  expect(await seriousAxe(visitor)).toEqual([]);

  await form.getByLabel("Your name").fill(`E2E Visit ${Date.now()}`);
  await form.getByLabel("Mobile number").fill(testMobile());
  await form.getByLabel("Time of day").selectOption("evening");
  await form.getByTestId("consent-required").check();
  await form.getByTestId("consent-marketing").check();
  await form.getByRole("button", { name: "Request a site visit" }).click();
  const success = visitor.getByTestId("lead-success");
  await expect(success).toContainText("Your reference:");
  const reference = (await success.locator(".tabular-nums").textContent())?.trim() ?? "";

  const lead = await leadByReference(page, reference);
  expect(lead.source).toBe("site_visit");
  expect(lead.marketing_consent).not.toBeNull();
  expect(lead.page_url).toBe("/contact");
  await visitorContext.close();
});

test("a gated brochure opens after the form", async ({ page, browser }) => {
  const project = await catalogueProject(page);
  await attachBrochure(page, project.id, true);
  const visitorContext = await browser.newContext();
  const visitor = await visitorContext.newPage();
  await visitor.goto(`/projects/${project.slug}`);
  // (That the API withholds a gated brochure's address is tested in the API suite.)
  await expect(visitor.getByTestId("brochure-download")).toHaveCount(0);
  await visitor.getByRole("link", { name: "Get the brochure" }).first().click();
  const form = visitor.getByTestId("lead-form-brochure");
  await form.getByLabel("Your name").fill(`E2E Brochure ${Date.now()}`);
  await form.getByLabel("Mobile number").fill(testMobile());
  await form.getByTestId("consent-required").check();
  await form.getByRole("button", { name: "Show the brochure" }).click();
  await expect(visitor.getByTestId("brochure-download")).toHaveAttribute(
    "href",
    /\.pdf$|\/files\//,
  );
  await visitorContext.close();
});

test("error answers are explained and nothing typed is lost (mocked, nothing submitted)", async ({
  page,
  browser,
}) => {
  const project = await catalogueProject(page);
  const visitorContext = await browser.newContext();
  const visitor = await visitorContext.newPage();
  await visitor.goto(`/projects/${project.slug}`);
  const form = visitor.getByTestId("lead-form-enquiry");
  await form.getByLabel("Your name").fill("E2E Mocked");
  await form.getByLabel("Mobile number").fill("12345");
  await form.getByTestId("consent-required").check();
  const send = form.getByRole("button", { name: "Request a call back" });
  const message = form.getByTestId("lead-message");

  const answers: [number, object | null, RegExp][] = [
    [
      422,
      {
        title: "Invalid",
        status: 422,
        errors: [{ field: "phone", message: "Enter a 10-digit Indian mobile number." }],
      },
      /check the highlighted fields/,
    ],
    [409, { title: "Conflict", status: 409 }, /reload the page/i],
    [429, { title: "Too many", status: 429 }, /wait a few minutes/],
    [503, { title: "Closed", status: 503 }, /aren't open yet/],
  ];
  for (const [status, body, expected] of answers) {
    await visitor.route("**/api/v1/public/leads", (route) =>
      route.fulfill({
        status,
        contentType: "application/problem+json",
        body: JSON.stringify(body),
      }),
    );
    await send.click();
    await expect(message).toContainText(expected);
    await expect(form.getByLabel("Your name")).toHaveValue("E2E Mocked");
    await visitor.unroute("**/api/v1/public/leads");
  }
  // The 422's field message sits under its field.
  await visitor.route("**/api/v1/public/leads", (route) =>
    route.fulfill({
      status: 422,
      contentType: "application/problem+json",
      body: JSON.stringify(answers[0]?.[1]),
    }),
  );
  await send.click();
  await expect(form.getByText("Enter a 10-digit Indian mobile number.")).toBeVisible();
  await visitor.unroute("**/api/v1/public/leads");

  // Offline.
  await visitor.route("**/api/v1/public/leads", (route) => route.abort("internetdisconnected"));
  await send.click();
  await expect(message).toContainText(/offline/);
  await visitorContext.close();
});

test("without JavaScript the page offers call or WhatsApp instead of the form", async ({
  page,
  browser,
}) => {
  const project = await catalogueProject(page);
  const context = await browser.newContext({ javaScriptEnabled: false });
  const visitor = await context.newPage();
  await visitor.goto(`/projects/${project.slug}`);
  await expect(visitor.getByTestId("lead-form-enquiry")).toHaveCount(0);
  await expect(visitor.getByTestId("lead-fallback").first()).toContainText("needs JavaScript");
  await context.close();
});

test("the contact page and forms work at 390 px", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const csp = watchCsp(page);
  await page.goto("/contact");
  await expect(page.getByRole("heading", { level: 1, name: "Talk to Empire" })).toBeVisible();
  await expect(page.getByTestId("lead-form-visit")).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
  expect(await seriousAxe(page)).toEqual([]);
  expect(csp).toEqual([]);
});
