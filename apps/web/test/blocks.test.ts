import { describe, expect, it, vi } from "vitest";

// Blocks import the lead form panel, whose data layer is server-only; not used by these tests.
vi.mock("server-only", () => ({}));
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  BlockView,
  isSafeHref,
  leadFormSetup,
  startsWithHero,
  statSourceLine,
  videoWatchUrl,
} from "../src/components/blocks/Blocks";

const media = {
  id: "m1",
  kind: "image",
  url: "/img.png",
  alt_text: "Tower A at dusk",
  label: "artist_impression",
  label_month: null,
  is_sample: false,
  width: 800,
  height: 600,
  thumbnail_url: null,
  format: "png",
  duration_s: null,
};

const rera = {
  authority: "UP-RERA",
  number: "UPRERAPRJ123456",
  qr: null,
  url: "https://up-rera.in/x",
};
const price = { on_request: false, min_inr: 6500000, max_inr: 9000000, note: null };
const area = { basis: "carpet", display_unit: "sqft", min_sqm: 90, max_sqm: 120 };
const project = {
  id: "p1",
  slug: "empire-heights",
  name: "Empire Heights",
  status: "under_construction",
  sales_status: "available",
  city: { name: "Lucknow", slug: "lucknow" },
  locality: { name: "Gomti Nagar", slug: "gomti-nagar" },
  configuration_labels: ["2 BHK"],
  property_types: ["apartment"],
  cover: media,
  is_featured: false,
  is_sample: false,
  possession_date: "2028-03-01",
  price,
  area,
  rera,
};
const property = {
  id: "h1",
  slug: "tower-a-1203",
  name: "Tower A 1203",
  bhk: 2,
  property_type: "apartment",
  sales_status: "available",
  is_sample: false,
  cover: media,
  price,
  area,
  project: { ...project, rera },
};

function render(type: string, data: Record<string, unknown>, first = false): string {
  return renderToStaticMarkup(
    React.createElement(BlockView, {
      block: { id: "b1", type, data, sort_order: 0, is_visible: true },
      first,
      path: "/about",
    }),
  );
}

describe("block helpers", () => {
  it("accepts only site paths and https links", () => {
    expect(isSafeHref("/contact")).toBe(true);
    expect(isSafeHref("https://empirebuildcon.com/x")).toBe(true);
    expect(isSafeHref("//evil.example")).toBe(false);
    expect(isSafeHref("javascript:alert(1)")).toBe(false);
    expect(isSafeHref("http://plain.example")).toBe(false);
    expect(isSafeHref(null)).toBe(false);
    expect(isSafeHref("/\\evil.example")).toBe(false);
    expect(isSafeHref("/\t/evil.example")).toBe(false);
    expect(isSafeHref("/\n/evil.example")).toBe(false);
  });

  it("states the source and date of every number (COMPLIANCE, D-035)", () => {
    expect(statSourceLine({ source: "Possession register", as_of: "2026-09-30" })).toBe(
      "As of 30 Sep 2026 · Source: Possession register",
    );
  });

  it("links to YouTube or Vimeo, never embeds, and refuses odd ids", () => {
    expect(videoWatchUrl("youtube", "dQw4w9WgXcQ")).toBe(
      "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    );
    expect(videoWatchUrl("vimeo", "123456789")).toBe("https://vimeo.com/123456789");
    expect(videoWatchUrl("youtube", 'x"><script>')).toBeNull();
    expect(videoWatchUrl("other", "abcdefghijk")).toBeNull();
  });
});

describe("leadFormSetup", () => {
  it("keeps the staff's choice when the form can be sent", () => {
    expect(leadFormSetup("site_visit", "empire-heights")).toEqual({
      intent: "visit",
      source: "site_visit",
    });
    expect(leadFormSetup("brochure", "empire-heights")).toEqual({
      intent: "brochure",
      source: "brochure",
    });
    expect(leadFormSetup("contact_form", "empire-heights")).toEqual({
      intent: "enquiry",
      source: "contact_form",
    });
    expect(leadFormSetup("project_form", "empire-heights")).toEqual({
      intent: "enquiry",
      source: "project_form",
    });
    expect(leadFormSetup("campaign", null)).toEqual({ intent: "enquiry", source: "campaign" });
  });

  it("asks a plain question when a site visit or brochure has no project", () => {
    expect(leadFormSetup("site_visit", null)).toEqual({
      intent: "enquiry",
      source: "contact_form",
    });
    expect(leadFormSetup("brochure", undefined)).toEqual({
      intent: "enquiry",
      source: "contact_form",
    });
  });
});

describe("BlockView", () => {
  it("makes a leading hero the h1, with its honest image label and safe buttons", () => {
    const html = render(
      "hero",
      {
        heading: "Delivering Happiness",
        image: media,
        cta: { label: "See projects", href: "/projects" },
        secondary_cta: { label: "Bad", href: "javascript:alert(1)" },
      },
      true,
    );
    expect(html).toContain("<h1");
    expect(html).toContain("Delivering Happiness");
    expect(html).toContain("Artist&#x27;s impression");
    expect(html).toContain('href="/projects"');
    expect(html).not.toContain("javascript:");
    expect(render("hero", { heading: "Later hero" }, false)).toContain("<h2");
  });

  it("renders formatted text as elements, never HTML", () => {
    const html = render("rich_text", { heading: "About", body: "We *build* homes.\n\n<b>x</b>" });
    expect(html).toMatch(/<strong[^>]*>build<\/strong>/);
    expect(html).toContain("&lt;b&gt;x&lt;/b&gt;");
  });

  it("shows each stat with its source and date", () => {
    const html = render("stats", {
      items: [
        { value: "1,200", label: "homes handed over", source: "Register", as_of: "2026-09-30" },
      ],
    });
    expect(html).toContain("1,200");
    expect(html).toContain("As of 30 Sep 2026 · Source: Register");
  });

  it("shows a YouTube video as a link with no iframe or script", () => {
    const html = render("video", {
      heading: "Site tour",
      provider: "youtube",
      video_id: "dQw4w9WgXcQ",
    });
    expect(html).toContain('href="https://www.youtube.com/watch?v=dQw4w9WgXcQ"');
    expect(html).not.toMatch(/<iframe|<script/);
  });

  it("shows an offer with its terms and no countdown", () => {
    const html = render("offer_banner", {
      offer: {
        id: "o1",
        title: "Festive offer",
        body: "No floor rise charges.",
        terms: "Valid on bookings till 15 Nov 2026.",
        terms_url: "/terms",
        placement: "home",
        image: null,
        cta_label: null,
        cta_url: null,
        project_slug: null,
      },
    });
    expect(html).toContain("Festive offer");
    expect(html).toContain("Valid on bookings till 15 Nov 2026.");
    expect(html).toContain("Terms and conditions");
    expect(html).not.toMatch(/countdown|ends in|hurry/i);
  });

  it("renders steps, columns, gallery, FAQs, testimonials, CTA and divider", () => {
    expect(render("steps", { items: [{ title: "Visit", text: "See the site" }] })).toContain(
      "Visit",
    );
    expect(
      render("columns", {
        columns: [
          { heading: "A", body: "x" },
          { heading: "B", body: "y" },
        ],
      }),
    ).toContain("md:grid-cols-2");
    expect(render("gallery", { images: [media] })).toContain("Tower A at dusk");
    expect(
      render("faq_list", {
        faqs: [
          {
            id: "f1",
            question: "Is it RERA registered?",
            answer: "Yes.",
            sort_order: 0,
            is_visible: true,
          },
        ],
      }),
    ).toContain("Is it RERA registered?");
    expect(
      render("testimonials", {
        testimonials: [
          {
            id: "t1",
            person_name: "A. Buyer",
            person_detail: null,
            quote: "Good",
            rating: null,
            photo: null,
          },
        ],
      }),
    ).toContain("A. Buyer");
    expect(render("cta", { label: "Call us", href: "/contact" })).toContain('href="/contact"');
    expect(render("divider", {})).toContain("star-rule");
  });

  it("shows an image with its caption and honest label", () => {
    const html = render("image", { image: media, caption: "Tower A" });
    expect(html).toContain("Tower A at dusk");
    expect(html).toContain("Tower A");
    expect(html).toContain("Artist&#x27;s impression");
  });

  it("plays a library video from its own file, with no third-party player", () => {
    const html = render("video", {
      heading: "Walkthrough",
      media: { ...media, kind: "video", url: "https://res.cloudinary.com/x/v.mp4" },
    });
    expect(html).toContain("<video");
    expect(html).toContain('src="https://res.cloudinary.com/x/v.mp4"');
    expect(html).not.toMatch(/<iframe|<script|youtube|vimeo/);
  });

  it("shows project and home grids as cards with the RERA line", () => {
    const grid = render("project_grid", { heading: "Projects", projects: [project] });
    expect(grid).toContain('data-testid="project-card"');
    expect(grid).toContain("UPRERAPRJ123456");
    const homes = render("property_grid", { heading: "Homes", properties: [property] });
    expect(homes).toContain('data-testid="property-card"');
    expect(homes).toContain("excludes GST");
  });

  it("shows the project's RERA block with a map block", () => {
    const html = render("map", {
      heading: "Where it is",
      project: {
        name: "Empire Heights",
        slug: "empire-heights",
        lat: 26.85,
        lng: 80.95,
        address: "Gomti Nagar",
        directions_url: "https://www.openstreetmap.org/directions",
        rera: { ...rera, qr: { ...media, url: "/qr.png", alt_text: "QR" } },
      },
    });
    // COMPLIANCE: the full block — number, QR and up-rera.in — not just a line.
    expect(html).toContain('data-testid="rera-block"');
    expect(html).toContain("UPRERAPRJ123456");
    expect(html).toContain("UP-RERA QR code for Empire Heights");
    expect(html).toContain("up-rera.in");
  });

  it("gives step and column titles an h2 when the block has no heading", () => {
    expect(render("steps", { items: [{ title: "Visit" }] })).toMatch(/<h2[^>]*>Visit/);
    expect(render("steps", { heading: "How", items: [{ title: "Visit" }] })).toMatch(
      /<h3[^>]*>Visit/,
    );
    expect(render("columns", { columns: [{ heading: "A", body: "x" }] })).toMatch(/<h2[^>]*>A/);
  });

  it("leaves out an unknown type and blocks with nothing resolved", () => {
    expect(render("marquee", { text: "x" })).toBe("");
    expect(render("gallery", { images: [] })).toBe("");
    expect(render("offer_banner", {})).toBe("");
    expect(render("project_grid", { projects: [] })).toBe("");
  });

  it("knows whether a page starts with a hero, by order and visibility", () => {
    const b = (type: string, sort_order: number, is_visible = true) => ({
      id: `${type}${sort_order}`,
      type,
      data: {},
      sort_order,
      is_visible,
    });
    expect(startsWithHero([b("rich_text", 2), b("hero", 1)])).toBe(true);
    expect(startsWithHero([b("hero", 1, false), b("rich_text", 2)])).toBe(false);
    expect(startsWithHero([])).toBe(false);
  });
});
