/**
 * Which ad and analytics platforms the website may load, and the CSP sources each needs
 * (task 6.3, D-058).
 *
 * A tag runs only when BOTH of these are true:
 *   1. its ID is set in CMS → Settings → Tracking (the public site sends it), and
 *   2. its platform is listed in the TRACKING_CSP environment variable ("google", "meta",
 *      comma-separated), which also opens the platform's hosts in the Content-Security-Policy
 *      (proxy.ts).
 * WHY two switches: an ID typed into the CMS alone must not widen the CSP. Allowing a script
 * host lets any page injection load scripts from it, so hosts are opened only by a deploy
 * setting, and only for the platforms in use.
 *
 * Hosts are from Google's "Using Content Security Policy" guide for the Google tag (GA4), Google
 * Ads and Tag Manager (developers.google.com/tag-platform/security/guides/csp, read 7 Nov 2026),
 * with google.co.in as India's Google domain; and the Meta Pixel's script
 * (connect.facebook.net) and beacon (www.facebook.com) hosts.
 */

export type TrackingPlatform = "google" | "meta";

export interface TrackingIds {
  gtm_id?: string | null;
  ga4_id?: string | null;
  google_ads_id?: string | null;
  meta_pixel_id?: string | null;
}

export interface CspSources {
  script: string[];
  img: string[];
  connect: string[];
  frame: string[];
}

const GOOGLE: CspSources = {
  script: [
    "https://www.googletagmanager.com",
    "https://www.googleadservices.com",
    "https://www.google.com",
  ],
  img: [
    "https://www.googletagmanager.com",
    "https://*.google-analytics.com",
    "https://*.google.com",
    "https://*.google.co.in",
    "https://*.g.doubleclick.net",
    "https://www.googleadservices.com",
    "https://pagead2.googlesyndication.com",
  ],
  connect: [
    "https://www.googletagmanager.com",
    "https://*.google-analytics.com",
    "https://*.analytics.google.com",
    "https://*.google.com",
    "https://*.google.co.in",
    "https://*.g.doubleclick.net",
    "https://ad.doubleclick.net",
    "https://www.googleadservices.com",
    "https://pagead2.googlesyndication.com",
  ],
  frame: ["https://www.googletagmanager.com"],
};

const META: CspSources = {
  script: ["https://connect.facebook.net"],
  img: ["https://www.facebook.com"],
  connect: ["https://www.facebook.com", "https://connect.facebook.net"],
  frame: [],
};

/** The platforms TRACKING_CSP allows. Unknown words are ignored. */
export function allowedPlatforms(value: string | undefined): Set<TrackingPlatform> {
  const found = new Set<TrackingPlatform>();
  for (const word of (value ?? "").split(",")) {
    const name = word.trim().toLowerCase();
    if (name === "google" || name === "meta") found.add(name);
  }
  return found;
}

/** The extra CSP sources for the allowed platforms (empty when none). */
export function cspSources(platforms: Set<TrackingPlatform>): CspSources {
  const out: CspSources = { script: [], img: [], connect: [], frame: [] };
  for (const platform of platforms) {
    const add = platform === "google" ? GOOGLE : META;
    for (const key of Object.keys(out) as (keyof CspSources)[]) {
      for (const host of add[key]) if (!out[key].includes(host)) out[key].push(host);
    }
  }
  return out;
}

/** The IDs the website may use: those set in the CMS whose platform TRACKING_CSP allows. */
export function usableIds(
  ids: TrackingIds | null | undefined,
  platforms: Set<TrackingPlatform>,
): TrackingIds | null {
  if (!ids) return null;
  const google = platforms.has("google");
  const usable: TrackingIds = {
    gtm_id: google ? ids.gtm_id || null : null,
    ga4_id: google ? ids.ga4_id || null : null,
    google_ads_id: google ? ids.google_ads_id || null : null,
    meta_pixel_id: platforms.has("meta") ? ids.meta_pixel_id || null : null,
  };
  return Object.values(usable).some(Boolean) ? usable : null;
}
