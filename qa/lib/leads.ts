/**
 * Helpers for the lead journeys: a published project to enquire about, the current lead-form
 * consent text, a public site-visit request made exactly as the website will make it, a lead
 * added by staff, and dates in India time.
 *
 * Public calls go through the website's /api proxy from a fresh request context with no session,
 * like a visitor's browser (SECURITY.md §3: public intake reads no session and needs no CSRF).
 *
 * WHY one public submission per run: intake allows 5 per 10 minutes per IP (ARCHITECTURE §8), and
 * every local run comes from the same address. Everything else is set up through staff routes.
 * Test leads use obviously fake names ("E2E Lead …") and a random mobile number, because public
 * intake only accepts real-shaped Indian numbers. They live only in the local `empire_dev`
 * database and nothing contacts them: alerts arrive in Phase 4 part 5 and skip test data there.
 */
import { randomInt } from "node:crypto";
import { expect, request as playwrightRequest, type Page } from "@playwright/test";
import { WEB_URL } from "./env";
import { apiCall, apiUpload, runId } from "./auth";
import { sampleQr } from "./files";

export interface ConsentRef {
  id: string;
  version: number;
  checkbox_label: string;
}

export interface ProjectRef {
  id: string;
  slug: string;
  name: string;
}

/** Today's date in India ("2026-10-24"), plus `days`. India has no daylight saving: +05:30. */
export function istDate(days = 0): string {
  const now = Date.now() + 330 * 60_000 + days * 86_400_000;
  return new Date(now).toISOString().slice(0, 10);
}

/**
 * A random Indian mobile number as a visitor would type it, like "98765 43210". Random per run,
 * so a run never links to an earlier run's lead as a repeat enquiry (same phone within 24 hours).
 */
export function testMobile(): string {
  const digits = `9${String(randomInt(0, 1_000_000_000)).padStart(9, "0")}`;
  return `${digits.slice(0, 5)} ${digits.slice(5)}`;
}

/** The current lead-form consent text, read the way the website will read it. */
export async function currentConsent(page: Page): Promise<ConsentRef> {
  const response = await apiCall(page, "GET", "/api/v1/admin/consent-texts?kind=lead_form");
  expect(response.status()).toBe(200);
  const texts = (await response.json()) as Array<ConsentRef & { is_current: boolean }>;
  const current = texts.find((text) => text.is_current);
  expect(current, "a current lead-form consent text (seeded in dev/test)").toBeTruthy();
  return current as ConsentRef;
}

/**
 * A published project made through the API: draft → RERA number → one configuration → a QR-like
 * PNG as the RERA QR → publish. Named "E2E Leads …" so it can't pass for a real project.
 */
export async function publishedProject(page: Page): Promise<ProjectRef> {
  const name = `E2E Leads ${runId()}`;
  const created = await apiCall(page, "POST", "/api/v1/admin/projects", {
    name,
    status: "ongoing",
  });
  expect(created.status()).toBe(201);
  const project = (await created.json()) as ProjectRef;
  const patched = await apiCall(page, "PATCH", `/api/v1/admin/projects/${project.id}`, {
    rera_number: `UPRERAPRJ-E2E-${runId().toUpperCase()}`,
  });
  expect(patched.status()).toBe(200);
  const configuration = await apiCall(
    page,
    "POST",
    `/api/v1/admin/projects/${project.id}/configurations`,
    { name: "3 BHK (test)", property_type: "apartment", bhk: 3 },
  );
  expect(configuration.status()).toBe(201);
  const qr = await apiUpload(page, "/api/v1/admin/media/images", {
    file: sampleQr(),
    title: `${name} QR`,
    attach_to: `project:${project.id}`,
    role: "rera_qr",
  });
  expect(qr.status()).toBe(201);
  const published = await apiCall(page, "POST", `/api/v1/admin/projects/${project.id}/publish`);
  expect(published.status(), await published.text()).toBe(200);
  return project;
}

export interface PublicVisit {
  reference: string;
  name: string;
  phone: string;
  campaign: string;
}

/** A visitor asks for a site visit tomorrow morning (`POST /public/site-visits`). */
export async function requestSiteVisit(
  project: ProjectRef,
  consent: ConsentRef,
): Promise<PublicVisit> {
  const run = runId();
  const visit = { name: `E2E Lead ${run}`, phone: testMobile(), campaign: `e2e-${run}` };
  const visitor = await playwrightRequest.newContext({ baseURL: WEB_URL });
  try {
    const response = await visitor.post("/api/v1/public/site-visits", {
      data: {
        name: visit.name,
        phone: visit.phone,
        source: "site_visit",
        project_slug: project.slug,
        page_url: `/projects/${project.slug}`,
        utm: { source: "e2e", medium: "test", campaign: visit.campaign },
        click_ids: { gclid: "e2e-test-click" },
        consent: { accepted: true, consent_text_id: consent.id, version: consent.version },
        marketing_consent: null,
        preferred_date: istDate(1),
        preferred_slot: "morning",
        website: "",
      },
    });
    expect(response.status(), await response.text()).toBe(201);
    const { reference } = (await response.json()) as { reference: string };
    return { ...visit, reference };
  } finally {
    await visitor.dispose();
  }
}

/**
 * Cancels the site visits that earlier runs left open, so the dashboard's "Upcoming site visits"
 * (the next five open visits from today on) has room for this run's visit.
 *
 * WHY: the browser suite shares `empire_dev`, and every run confirms a visit for tomorrow. After
 * a few runs on one day those earlier visits fill the five places and push this run's visit off
 * the dashboard, although it is there. Only test visits ("E2E Lead …") made more than
 * `olderThanMinutes` ago are cancelled, so visits other specs of this run made, and the seeded
 * sample visits, stay as they are.
 */
export async function cancelEarlierTestVisits(
  page: Page,
  olderThanMinutes = 20,
  exceptLeadName?: string,
): Promise<void> {
  const response = await apiCall(
    page,
    "GET",
    `/api/v1/admin/site-visits?open=true&from=${istDate(-7)}&to=${istDate(60)}`,
  );
  expect(response.status()).toBe(200);
  const visits = (await response.json()) as Array<{
    id: string;
    lead_name: string;
    is_sample: boolean;
    created_at: string;
  }>;
  const cutoff = Date.now() - olderThanMinutes * 60_000;
  for (const visit of visits) {
    if (visit.is_sample || !visit.lead_name.startsWith("E2E Lead ")) continue;
    if (exceptLeadName && visit.lead_name === exceptLeadName) continue;
    if (Date.parse(visit.created_at) >= cutoff) continue;
    const cancelled = await apiCall(page, "PATCH", `/api/v1/admin/site-visits/${visit.id}`, {
      status: "cancelled",
    });
    expect(cancelled.status(), await cancelled.text()).toBe(200);
  }
}

/** A lead typed in by staff (`POST /admin/leads`), optionally given to someone. */
export async function manualLead(
  page: Page,
  name: string,
  ownerUserId?: string | null,
  options: { phone?: string; projectId?: string } = {},
): Promise<{ id: string; reference: string }> {
  const response = await apiCall(page, "POST", "/api/v1/admin/leads", {
    name,
    phone: options.phone ?? testMobile(),
    source: "phone",
    consent_note: "Verbal on phone call (browser test)",
    ...(options.projectId ? { project_id: options.projectId } : {}),
    ...(ownerUserId === undefined ? {} : { owner_user_id: ownerUserId }),
  });
  expect(response.status(), await response.text()).toBe(201);
  return (await response.json()) as { id: string; reference: string };
}

/** The id of the seeded "Sample — Project A" (dev/test only). */
export async function sampleProjectId(page: Page): Promise<string> {
  const response = await apiCall(page, "GET", "/api/v1/admin/projects?q=sample-project-a");
  expect(response.status()).toBe(200);
  const { items } = (await response.json()) as { items: Array<{ id: string; slug: string }> };
  const project = items.find((item) => item.slug === "sample-project-a");
  expect(project, "the sample project from `empire-api seed --sample`").toBeTruthy();
  return (project as { id: string }).id;
}
