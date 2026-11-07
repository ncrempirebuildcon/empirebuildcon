// @vitest-environment jsdom
/**
 * Tags after consent (task 6.3, D-058): which platforms and IDs may run, and what loads for each
 * cookie choice. COMPLIANCE: nothing without a choice; analytics and marketing kept apart.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { Consent } from "../src/lib/consent";
import { allowedPlatforms, cspSources, usableIds } from "../src/lib/tracking/platforms";
import {
  applyConsent,
  loadedTags,
  needsReload,
  resetTagsForTests,
  trackLead,
  trackPageView,
} from "../src/lib/tracking/tags";

const IDS = {
  gtm_id: null,
  ga4_id: "G-AB12CD34EF",
  google_ads_id: "AW-123456789",
  meta_pixel_id: "123456789012345",
};

function choice(analytics: boolean, marketing: boolean): Consent {
  return { v: 1, analytics, marketing, at: new Date().toISOString() };
}

function scripts(): string[] {
  return [...document.head.querySelectorAll("script[src]")].map(
    (s) => (s as HTMLScriptElement).src,
  );
}

/** dataLayer entries as plain arrays (gtag pushes `arguments` objects). */
function layer(): unknown[][] {
  return (window.dataLayer ?? []).map((entry) =>
    Array.isArray(entry) || typeof entry !== "object" || entry === null
      ? (entry as unknown[])
      : Array.from(entry as ArrayLike<unknown>),
  );
}

beforeEach(() => {
  document.head.innerHTML = "";
  resetTagsForTests();
});
afterEach(() => resetTagsForTests());

describe("platforms and IDs", () => {
  it("reads TRACKING_CSP, ignoring case, spaces and unknown words", () => {
    expect([...allowedPlatforms(" Google, meta ,x")]).toEqual(["google", "meta"]);
    expect(allowedPlatforms(undefined).size).toBe(0);
  });

  it("gives no extra CSP hosts when nothing is allowed", () => {
    expect(cspSources(new Set())).toEqual({ script: [], img: [], connect: [], frame: [] });
  });

  it("uses only IDs whose platform is allowed; none usable → null (no banner, no tags)", () => {
    expect(usableIds(IDS, new Set())).toBeNull();
    expect(usableIds(IDS, new Set(["meta"]))).toEqual({
      gtm_id: null,
      ga4_id: null,
      google_ads_id: null,
      meta_pixel_id: IDS.meta_pixel_id,
    });
    expect(usableIds(null, new Set(["google", "meta"]))).toBeNull();
    expect(usableIds({ meta_pixel_id: IDS.meta_pixel_id }, new Set(["google"]))).toBeNull();
  });
});

describe("what loads for each choice", () => {
  it("rejecting everything loads nothing", () => {
    applyConsent(choice(false, false), IDS);
    expect(scripts()).toEqual([]);
    expect(window.dataLayer).toBeUndefined();
    expect(window.fbq).toBeUndefined();
  });

  it("analytics only: GA4, consent denied by default then analytics granted; no ads, no Pixel", () => {
    applyConsent(choice(true, false), IDS);
    expect(scripts()).toEqual(["https://www.googletagmanager.com/gtag/js?id=G-AB12CD34EF"]);
    const entries = layer();
    expect(entries[0]).toEqual([
      "consent",
      "default",
      {
        analytics_storage: "denied",
        ad_storage: "denied",
        ad_user_data: "denied",
        ad_personalization: "denied",
      },
    ]);
    expect(entries[1]).toEqual([
      "consent",
      "update",
      {
        analytics_storage: "granted",
        ad_storage: "denied",
        ad_user_data: "denied",
        ad_personalization: "denied",
      },
    ]);
    expect(entries.some((e) => e[0] === "config" && e[1] === "G-AB12CD34EF")).toBe(true);
    expect(entries.some((e) => e[0] === "config" && e[1] === "AW-123456789")).toBe(false);
    expect(window.fbq).toBeUndefined();
  });

  it("marketing only: Google Ads and the Pixel; ad personalisation stays denied; no GA4", () => {
    applyConsent(choice(false, true), IDS);
    expect(scripts()).toContain("https://connect.facebook.net/en_US/fbevents.js");
    const entries = layer();
    const update = entries.find((e) => e[0] === "consent" && e[1] === "update");
    expect(update?.[2]).toMatchObject({
      analytics_storage: "denied",
      ad_storage: "granted",
      ad_personalization: "denied",
    });
    expect(entries.some((e) => e[0] === "config" && e[1] === "AW-123456789")).toBe(true);
    expect(entries.some((e) => e[0] === "config" && e[1] === "G-AB12CD34EF")).toBe(false);
    expect(window.fbq?.queue).toContainEqual(["init", IDS.meta_pixel_id]);
  });

  it("loads each script once, even when the choice is applied again", () => {
    applyConsent(choice(true, true), IDS);
    applyConsent(choice(true, true), IDS);
    expect(scripts()).toHaveLength(2);
  });

  it("Tag Manager loads only with both choices: its container can hold any tag", () => {
    applyConsent(choice(true, false), { gtm_id: "GTM-AB12CD3" });
    applyConsent(choice(false, true), { gtm_id: "GTM-AB12CD3" });
    expect(scripts()).toEqual([]);
    applyConsent(choice(true, true), { gtm_id: "GTM-AB12CD3" });
    expect(scripts()).toEqual(["https://www.googletagmanager.com/gtm.js?id=GTM-AB12CD3"]);
    expect(layer()[0]?.[1]).toBe("default");
    expect(needsReload(choice(true, false))).toBe(true);
  });

  it("with marketing only, the Google tag loads under the Ads ID, not GA4's", () => {
    applyConsent(choice(false, true), IDS);
    expect(scripts()).toContain("https://www.googletagmanager.com/gtag/js?id=AW-123456789");
    expect(scripts().some((src) => src.includes("G-AB12CD34EF"))).toBe(false);
  });

  it("scripts carry the page's CSP nonce", () => {
    const marker = document.createElement("script");
    marker.setAttribute("nonce", "n0nce");
    document.head.appendChild(marker);
    applyConsent(choice(true, false), IDS);
    const added = document.head.querySelector<HTMLScriptElement>("script[src]");
    expect(added?.nonce || added?.getAttribute("nonce")).toBe("n0nce");
  });
});

describe("narrowing a choice and events", () => {
  it("asks for a reload only when something loaded is no longer allowed", () => {
    expect(needsReload(choice(false, false))).toBe(false); // nothing loaded yet
    applyConsent(choice(true, true), IDS);
    expect(needsReload(choice(true, true))).toBe(false);
    expect(needsReload(choice(true, false))).toBe(true); // ads and Pixel loaded
    expect(needsReload(null)).toBe(true);
  });

  it("a lead reaches GA4 and the Pixel with the reference as Meta's eventID", () => {
    applyConsent(choice(true, true), IDS);
    trackLead(IDS, "EMP-00042");
    expect(layer().some((e) => e[0] === "event" && e[1] === "generate_lead")).toBe(true);
    expect(window.fbq?.queue).toContainEqual(["track", "Lead", {}, { eventID: "EMP-00042" }]);
  });

  it("page views go only to loaded tags, once per address", () => {
    applyConsent(choice(true, false), IDS);
    trackPageView(IDS);
    trackPageView(IDS); // a re-saved choice or another tab: nothing more
    const views = () => layer().filter((e) => e[0] === "event" && e[1] === "page_view").length;
    expect(views()).toBe(1);
    expect(loadedTags().pixel).toBe(false);

    applyConsent(choice(true, true), IDS); // widened: the Pixel gets this page, GA4 nothing new
    trackPageView(IDS);
    expect(views()).toBe(1);
    expect(window.fbq?.queue.filter((q) => q[1] === "PageView")).toHaveLength(1);
  });
});
