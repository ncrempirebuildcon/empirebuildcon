import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import MobileActionBar from "../src/components/shell/MobileActionBar";
import Footer from "../src/components/shell/Footer";
import SampleDataRibbon from "../src/components/shell/SampleDataRibbon";
import OfferBanner from "../src/components/shell/OfferBanner";
import type { PublicSite, PublicOffer } from "../src/lib/public/api";

const sampleCompany: PublicSite["company"] = {
  legal_name: "Empire Buildcon Private Limited",
  name: "Empire",
  tagline: "Luxury real estate in Uttar Pradesh",
  address: "123 Gomti Nagar, Lucknow",
  corporate_address: "[Main Office Address Placeholder]",
  registered_address: null,
  gstin: null,
  phones: ["+91 98765 43210", "[Phone Placeholder]"],
  emails: ["info@empirebuildcon.com", "[Email Placeholder]"],
  whatsapp: "[WhatsApp Placeholder]",
  whatsapp_message: "Enquiring about {page}",
  office_hours: "[Hours Placeholder]",
};

describe("MobileActionBar Component (S6)", () => {
  it("renders nothing when neither phone nor WhatsApp is configured", () => {
    const html = renderToStaticMarkup(
      React.createElement(MobileActionBar, {
        company: { ...sampleCompany, phones: [], whatsapp: null },
      }),
    );
    expect(html).toBe("");
  });

  it("renders nothing in production when all numbers are placeholders", () => {
    const placeholderCompany: PublicSite["company"] = {
      ...sampleCompany,
      phones: ["[Placeholder Phone]"],
      whatsapp: "[Placeholder WhatsApp]",
    };
    const html = renderToStaticMarkup(
      React.createElement(MobileActionBar, {
        company: placeholderCompany,
        isProduction: true,
      }),
    );
    expect(html).toBe("");
  });

  it("renders Call and WhatsApp when numbers are valid", () => {
    const validCompany = { ...sampleCompany, whatsapp: "+91 98765 43211" };
    const html = renderToStaticMarkup(
      React.createElement(MobileActionBar, {
        company: validCompany,
        isProduction: false,
      }),
    );
    expect(html).toContain("Call");
    expect(html).toContain("WhatsApp");
    expect(html).toContain("Enquire");
    expect(html).toContain("tel:+919876543210");
    expect(html).toContain("wa.me/919876543211");
  });

  it("falls back to phone for WhatsApp in production when whatsapp is placeholder", () => {
    const html = renderToStaticMarkup(
      React.createElement(MobileActionBar, {
        company: sampleCompany,
        isProduction: true,
      }),
    );
    expect(html).toContain("tel:+919876543210");
    expect(html).toContain("wa.me/919876543210");
  });
});

describe("SampleDataRibbon Component (S7, S-N4)", () => {
  it("renders sample notice in dev/staging when hasSampleData is true", () => {
    const html = renderToStaticMarkup(
      React.createElement(SampleDataRibbon, { hasSampleData: true }),
    );
    expect(html).toContain("Sample data");
    expect(html).toContain(
      "project names, prices, RERA numbers and images are placeholders for review",
    );
  });

  it("renders nothing when hasSampleData is false", () => {
    const html = renderToStaticMarkup(
      React.createElement(SampleDataRibbon, { hasSampleData: false }),
    );
    expect(html).toBe("");
  });
});

describe("OfferBanner Component (S8, S-N4)", () => {
  const sampleOffer: PublicOffer = {
    id: "11111111-1111-1111-1111-111111111111",
    title: "Diwali Special Offer",
    body: "No pre-EMI until possession",
    cta_label: "Claim offer",
    cta_url: "/contact#offer",
    placement: "banner",
    project_slug: "gomti-greens",
    terms: "T&C apply",
    terms_url: "/terms",
    image: null,
    starts_at: "2026-10-01T00:00:00Z",
    ends_at: "2026-11-15T00:00:00Z",
  };

  it("renders validity date range when starts_at and ends_at are present (S-N4)", () => {
    const html = renderToStaticMarkup(React.createElement(OfferBanner, { offers: [sampleOffer] }));
    expect(html).toContain("Diwali Special Offer");
    expect(html).toContain("Valid 1 Oct 2026 – 15 Nov 2026");
  });
});

describe("Footer Component (S8)", () => {
  const dummySite: PublicSite = {
    company: sampleCompany,
    regulator: {
      authority: "UP-RERA",
      name: "UP Real Estate Regulatory Authority",
      promoter_number: "PRM/UP/0001",
      state: "UP",
      website: "https://up-rera.in",
    },
    social: {
      facebook: "https://facebook.com/empire",
      instagram: "https://instagram.com/empire",
      youtube: "[YouTube Placeholder]",
    },
    nav: [],
    offers: [],
    consent: {},
    features: {},
    locales: ["en"],
    seo: null,
    has_sample: false,
    tracking: {
      ga4_id: null,
      gtm_id: null,
      meta_pixel_id: null,
    },
  };

  it("hides placeholder addresses, emails, and social links in production", () => {
    const html = renderToStaticMarkup(
      React.createElement(Footer, {
        site: dummySite,
        isProduction: true,
      }),
    );

    // Legitimate values present
    expect(html).toContain("123 Gomti Nagar, Lucknow");
    expect(html).toContain("info@empirebuildcon.com");
    expect(html).toContain("+91 98765 43210");

    // Placeholders hidden
    expect(html).not.toContain("[Main Office Address Placeholder]");
    expect(html).not.toContain("[Email Placeholder]");
    expect(html).not.toContain("[Hours Placeholder]");

    // Social links rendered (placeholder YouTube dropped)
    expect(html).toContain("Follow Empire on facebook");
    expect(html).toContain("Follow Empire on instagram");
    expect(html).not.toContain("Follow Empire on youtube");
    // 44 px target on social icons (Note 5)
    expect(html).toContain("min-h-[44px] min-w-[44px]");
  });
});
