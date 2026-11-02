import { describe, expect, it } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { LeadForm } from "../src/components/leads/LeadForm";
import {
  attributionFromSearch,
  cleanReferrer,
  ENDPOINT,
  leadBody,
  mergeAttribution,
  OFFLINE_MESSAGE,
  outcomeFor,
  pagePath,
  visitDateRange,
  type LeadInput,
} from "../src/lib/public/leads";

const consent = { id: "11111111-1111-1111-1111-111111111111", version: 3 };
const marketing = { id: "22222222-2222-2222-2222-222222222222", version: 1 };
const base: LeadInput = {
  name: "  Asha Verma ",
  phone: " 98765 43210 ",
  email: "",
  message: "",
  projectSlug: "aurum",
  consent,
  marketing,
  marketingTicked: false,
  website: "",
};
const ctx = {
  pathname: "/projects/aurum",
  referrer: "https://www.google.com/search?q=asha+98765",
  attribution: { utm: { source: "google" }, click_ids: { gclid: "abc" } },
};

describe("leadBody (COMPLIANCE)", () => {
  it("names the exact consent text and leaves marketing out unless ticked", () => {
    const body = leadBody("enquiry", base, ctx);
    expect(body.consent).toEqual({
      accepted: true,
      consent_text_id: consent.id,
      version: 3,
    });
    expect(body.marketing_consent).toBeNull();
    expect(body.name).toBe("Asha Verma");
    expect(body.phone).toBe("98765 43210");
    expect(body.email).toBeNull();
    expect(body.message).toBeNull();
    expect(body.source).toBe("project_form");
    expect(body.website).toBe("");
  });

  it("sends marketing consent only with its own text when ticked", () => {
    const body = leadBody("enquiry", { ...base, marketingTicked: true }, ctx);
    expect(body.marketing_consent).toEqual({
      accepted: true,
      consent_text_id: marketing.id,
      version: 1,
    });
    // Ticked but no current marketing text: nothing is invented.
    const none = leadBody("enquiry", { ...base, marketingTicked: true, marketing: null }, ctx);
    expect(none.marketing_consent).toBeNull();
  });

  it("sends the path only and a referrer without its query", () => {
    const body = leadBody("enquiry", base, {
      ...ctx,
      pathname: "/projects/aurum",
    });
    expect(body.page_url).toBe("/projects/aurum");
    expect(body.referrer).toBe("https://www.google.com/search");
    expect(body.utm).toEqual({ source: "google" });
    expect(body.click_ids).toEqual({ gclid: "abc" });
  });

  it("adds the visit day and slot only for a visit, and picks the source per intent", () => {
    const visit = leadBody(
      "visit",
      { ...base, preferredDate: "2026-11-10", preferredSlot: "evening" },
      ctx,
    );
    expect(visit).toMatchObject({
      source: "site_visit",
      preferred_date: "2026-11-10",
      preferred_slot: "evening",
    });
    const enquiry = leadBody("enquiry", base, ctx);
    expect(enquiry).not.toHaveProperty("preferred_date");
    expect(leadBody("brochure", base, ctx).source).toBe("brochure");
    expect(leadBody("enquiry", { ...base, projectSlug: null }, ctx).source).toBe("contact_form");
    expect(ENDPOINT.visit).toBe("/api/v1/public/site-visits");
  });

  it("passes the honeypot through as filled, so the API can catch bots", () => {
    expect(leadBody("enquiry", { ...base, website: "spam.example" }, ctx).website).toBe(
      "spam.example",
    );
  });
});

describe("attribution", () => {
  it("keeps only UTM tags and click IDs, trimmed and capped", () => {
    const a = attributionFromSearch(
      `?utm_source=fb&utm_medium=%20cpc%20&utm_bogus=x&gclid=G1&email=a@b.c&utm_campaign=${"x".repeat(300)}`,
    );
    expect(a?.utm.source).toBe("fb");
    expect(a?.utm.medium).toBe("cpc");
    expect(a?.utm.campaign).toHaveLength(200);
    expect(a?.click_ids).toEqual({ gclid: "G1" });
    expect(JSON.stringify(a)).not.toContain("email");
    expect(attributionFromSearch("?q=flats")).toBeNull();
  });

  it("keeps the first touch for the session and survives rubbish in storage", () => {
    const first = JSON.stringify({ utm: { source: "google" }, click_ids: {} });
    const later = attributionFromSearch("?utm_source=facebook");
    expect(mergeAttribution(first, later).utm.source).toBe("google");
    expect(mergeAttribution(null, later).utm.source).toBe("facebook");
    expect(mergeAttribution("{not json", later).utm.source).toBe("facebook");
    expect(mergeAttribution(null, null)).toEqual({ utm: {}, click_ids: {} });
    // A hand-edited store can't add other keys.
    const edited = JSON.stringify({ utm: { source: "g", phone: "987" }, click_ids: { x: "1" } });
    expect(mergeAttribution(edited, null)).toEqual({ utm: { source: "g" }, click_ids: {} });
  });

  it("accepts only web referrers and paths", () => {
    expect(cleanReferrer("javascript:alert(1)")).toBeNull();
    expect(cleanReferrer("")).toBeNull();
    expect(cleanReferrer("not a url")).toBeNull();
    expect(cleanReferrer("http://example.com/a#b")).toBe("http://example.com/a");
    expect(pagePath("/contact")).toBe("/contact");
    expect(pagePath("weird")).toBe("/");
  });
});

describe("outcomeFor", () => {
  it("reads a success with the reference and the brochure link", () => {
    expect(
      outcomeFor(201, { reference: "EMP-1", message: "Thanks", url: "https://x/b.pdf" }),
    ).toEqual({
      kind: "ok",
      reference: "EMP-1",
      message: "Thanks",
      brochureUrl: "https://x/b.pdf",
    });
  });

  it("puts field errors under their fields and the rest at the top", () => {
    const o = outcomeFor(422, {
      title: "Invalid",
      errors: [
        { field: "body.phone", message: "Enter a 10-digit Indian number." },
        { field: "consent", message: "x" },
      ],
    });
    expect(o).toEqual({
      kind: "fields",
      fields: { phone: "Enter a 10-digit Indian number." },
      message: "Please check the highlighted fields.",
    });
    expect(outcomeFor(422, { detail: "Something else." })).toMatchObject({
      kind: "fields",
      message: "Something else.",
    });
  });

  it("explains 409, 429, 503, 404 and anything else", () => {
    expect(outcomeFor(409, {}).kind).toBe("reload");
    expect(outcomeFor(429, {}).message).toMatch(/wait a few minutes/);
    expect(outcomeFor(503, {}).message).toMatch(/aren't open yet/);
    expect(outcomeFor(404, {}).message).toMatch(/isn't available/);
    expect(outcomeFor(500, null).message).toMatch(/couldn't send/);
    expect(outcomeFor(201, {}).kind).toBe("error"); // a 201 without a reference isn't trusted
    expect(OFFLINE_MESSAGE).toMatch(/offline/);
  });
});

describe("visitDateRange", () => {
  it("runs from today to 120 days ahead in India time", () => {
    // 20:00 UTC on 2 Nov is already 3 Nov in India.
    const r = visitDateRange(new Date("2026-11-02T20:00:00Z"));
    expect(r).toEqual({ min: "2026-11-03", max: "2027-03-03" });
  });
});

describe("LeadForm before hydration and without a consent text", () => {
  const fallback = React.createElement("p", null, "Call or WhatsApp us");
  const text = { id: "t", version: 1, body: "Full text", checkbox_label: "Contact me" };

  it("renders the fallback, not the form, on the server (what a no-JavaScript visitor sees)", () => {
    const html = renderToStaticMarkup(
      React.createElement(LeadForm, {
        intent: "enquiry",
        title: "Talk to us",
        consent: text,
        marketing: null,
        fallback,
        submitLabel: "Send",
      }),
    );
    expect(html).toContain("Call or WhatsApp us");
    expect(html).not.toContain("<form");
  });

  it("shows no form at all without a current lead-form text (COMPLIANCE)", () => {
    const html = renderToStaticMarkup(
      React.createElement(LeadForm, {
        intent: "visit",
        title: "Book a site visit",
        consent: null,
        marketing: text,
        fallback,
        submitLabel: "Send",
      }),
    );
    expect(html).toContain('data-testid="lead-form-closed"');
    expect(html).toContain("Call or WhatsApp us");
    expect(html).not.toContain("<form");
    expect(html).not.toContain("Contact me");
  });
});
