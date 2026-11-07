/**
 * Loading Google and Meta tags after the visitor's cookie choice (task 6.3, D-058).
 *
 * COMPLIANCE (DPDP Act, D-055):
 *   - Nothing here runs before a choice: `applyConsent` is called only with a stored choice.
 *   - Analytics consent → GA4. Marketing consent → Google Ads and the Meta Pixel. Tag Manager
 *     needs both, because its container can hold any tag.
 *   - Google Consent Mode v2 starts with everything denied and is updated to the choice before
 *     any Google tag is configured. `ad_personalization` stays denied: the banner asks to
 *     "measure which ads bring visitors", not to personalise ads (as D-057).
 *   - A tag can't be unloaded. When a choice is narrowed after a tag loaded, the page reloads,
 *     so from then on only what is allowed runs (`needsReload`).
 * SECURITY: scripts are added as elements with the page's CSP nonce (Tag Manager passes it on to
 * the tags it adds) and load only from hosts the CSP allows (platforms.ts). No inline script.
 */
import type { Consent } from "@/lib/consent";
import type { TrackingIds } from "./platforms";

type Gtag = (...args: unknown[]) => void;
type Fbq = ((...args: unknown[]) => void) & {
  callMethod?: (...args: unknown[]) => void;
  queue: unknown[][];
  loaded?: boolean;
  version?: string;
  push?: unknown;
};

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: Gtag;
    fbq?: Fbq;
    _fbq?: Fbq;
  }
}

export interface Loaded {
  googleTag: boolean;
  gtm: boolean;
  ga4: boolean;
  ads: boolean;
  pixel: boolean;
}

export const NOTHING_LOADED: Loaded = {
  googleTag: false,
  gtm: false,
  ga4: false,
  ads: false,
  pixel: false,
};

let loaded: Loaded = { ...NOTHING_LOADED };
/** The address each tag last got a page view for (trackPageView). */
const viewed = { ga4: "", pixel: "" };

/** For tests only. */
export function resetTagsForTests(): void {
  loaded = { ...NOTHING_LOADED };
  viewed.ga4 = "";
  viewed.pixel = "";
  delete window.dataLayer;
  delete window.gtag;
  delete window.fbq;
  delete window._fbq;
}

export function loadedTags(): Loaded {
  return { ...loaded };
}

function pageNonce(): string | undefined {
  const withNonce = document.querySelector<HTMLScriptElement>("script[nonce]");
  return withNonce?.nonce || withNonce?.getAttribute("nonce") || undefined;
}

function addScript(src: string): void {
  const script = document.createElement("script");
  script.async = true;
  script.src = src;
  const nonce = pageNonce();
  if (nonce) script.nonce = nonce;
  document.head.appendChild(script);
}

function gtag(...args: unknown[]): void {
  window.dataLayer = window.dataLayer || [];
  // Google's tag reads the `arguments` object pushed onto dataLayer, not an array.
  window.gtag =
    window.gtag ||
    function gtagShim() {
      // eslint-disable-next-line prefer-rest-params
      window.dataLayer!.push(arguments);
    };
  window.gtag(...args);
}

function consentState(consent: Consent): Record<string, "granted" | "denied"> {
  return {
    analytics_storage: consent.analytics ? "granted" : "denied",
    ad_storage: consent.marketing ? "granted" : "denied",
    ad_user_data: consent.marketing ? "granted" : "denied",
    ad_personalization: "denied",
  };
}

function ensureFbq(): Fbq {
  if (window.fbq) return window.fbq;
  // The Meta Pixel's documented stub: calls queue until fbevents.js loads and replays them.
  const fbq = function (...args: unknown[]) {
    if (fbq.callMethod) fbq.callMethod(...args);
    else fbq.queue.push(args);
  } as Fbq;
  fbq.queue = [];
  fbq.loaded = true;
  fbq.version = "2.0";
  fbq.push = fbq;
  window.fbq = fbq;
  window._fbq = fbq;
  return fbq;
}

/** True when the new choice withdraws something already loaded (a reload is the only way out). */
export function needsReload(consent: Consent | null): boolean {
  const analytics = Boolean(consent?.analytics);
  const marketing = Boolean(consent?.marketing);
  return (
    (!analytics && loaded.ga4) ||
    (!marketing && (loaded.ads || loaded.pixel)) ||
    ((!analytics || !marketing) && loaded.gtm) ||
    (!analytics && !marketing && loaded.googleTag)
  );
}

/** Load (once) whatever the choice allows. Safe to call again with a wider choice. */
export function applyConsent(consent: Consent, ids: TrackingIds): void {
  const wantGa4 = consent.analytics && Boolean(ids.ga4_id);
  const wantAds = consent.marketing && Boolean(ids.google_ads_id);
  // WHY both: a Tag Manager container can hold any tag (a Custom HTML Pixel ignores Consent
  // Mode), so it runs only when the visitor allowed analytics AND marketing (6.3 review).
  const wantGtm = consent.analytics && consent.marketing && Boolean(ids.gtm_id);
  const wantPixel = consent.marketing && Boolean(ids.meta_pixel_id);

  if (wantGa4 || wantAds || wantGtm) {
    if (!loaded.googleTag && !loaded.gtm) {
      gtag("consent", "default", {
        analytics_storage: "denied",
        ad_storage: "denied",
        ad_user_data: "denied",
        ad_personalization: "denied",
      });
    }
    gtag("consent", "update", consentState(consent));
  }
  if ((wantGa4 || wantAds) && !loaded.googleTag) {
    gtag("js", new Date());
    addScript(
      `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent((wantGa4 ? ids.ga4_id : ids.google_ads_id)!)}`,
    );
    loaded.googleTag = true;
  }
  if (wantGa4 && !loaded.ga4) {
    // Page views are sent by `trackPageView`, also on client-side navigation.
    gtag("config", ids.ga4_id, { send_page_view: false });
    loaded.ga4 = true;
  }
  if (wantAds && !loaded.ads) {
    gtag("config", ids.google_ads_id, { send_page_view: false });
    loaded.ads = true;
  }
  if (wantGtm && !loaded.gtm) {
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({ "gtm.start": Date.now(), event: "gtm.js" });
    addScript(`https://www.googletagmanager.com/gtm.js?id=${encodeURIComponent(ids.gtm_id!)}`);
    loaded.gtm = true;
  }
  if (wantPixel && !loaded.pixel) {
    const fbq = ensureFbq();
    addScript("https://connect.facebook.net/en_US/fbevents.js");
    fbq("init", ids.meta_pixel_id);
    loaded.pixel = true;
  }
}

/**
 * One page view per address to each loaded tag: the first view, every client-side navigation,
 * and the current page for a tag that has just loaded. Calling it again for the same address
 * sends nothing (a re-saved choice, another tab, a refresh of the props; 6.3 review).
 */
export function trackPageView(ids: TrackingIds): void {
  const here = window.location.href;
  if (loaded.ga4 && viewed.ga4 !== here) {
    gtag("event", "page_view", {
      send_to: ids.ga4_id,
      page_location: here,
      page_title: document.title,
    });
    viewed.ga4 = here;
  }
  if (loaded.pixel && viewed.pixel !== here) {
    window.fbq?.("track", "PageView");
    viewed.pixel = here;
  }
}

/**
 * A sent enquiry. `reference` is the eventID Meta uses to count this and the server's Lead event
 * (6.2, which uses the same reference) once. Google Ads hears about leads from the server only,
 * so the browser sends it nothing here.
 */
export function trackLead(ids: TrackingIds, reference: string): void {
  if (loaded.ga4) gtag("event", "generate_lead", { send_to: ids.ga4_id });
  if (loaded.pixel) window.fbq?.("track", "Lead", {}, { eventID: reference });
}
