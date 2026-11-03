/**
 * Lead form rules for the public site (task 5.4, D-043): the request body, attribution
 * (UTM tags and click IDs), and how API answers become messages. Pure functions, so they are
 * unit-tested without a browser (test/leads.test.ts).
 *
 * COMPLIANCE (AGENTS.md "Consent", D-017, SECURITY.md §8):
 *   - The required consent names the exact text the visitor saw (id + version).
 *   - Marketing consent is sent only when its box was ticked; never assumed.
 *   - `page_url` is the path only: a query string can hold a phone number or a token.
 *   - Attribution stays in this browser tab's session storage, not a cookie, and only the keys
 *     below are kept. Nothing goes to a third party (tracking waits for Phase 6's banner).
 */

export type LeadIntent = "enquiry" | "visit" | "brochure";
export type VisitSlot = "morning" | "afternoon" | "evening";

export interface ConsentRef {
  id: string;
  version: number;
}

export interface LeadInput {
  name: string;
  phone: string;
  email?: string;
  message?: string;
  projectSlug?: string | null;
  configurationId?: string | null;
  preferredDate?: string;
  preferredSlot?: VisitSlot;
  consent: ConsentRef;
  /** The marketing text, sent only when `marketingTicked` is true. */
  marketing?: ConsentRef | null;
  marketingTicked: boolean;
  /** The honeypot as the browser filled it (people never see it, so it's normally ""). */
  website: string;
  /** A page-builder form's own source (e.g. "campaign"); otherwise chosen from the intent. */
  source?: "project_form" | "contact_form" | "campaign" | "site_visit" | "brochure";
}

export interface Attribution {
  utm: Partial<Record<(typeof UTM_KEYS)[number], string>>;
  click_ids: Partial<Record<(typeof CLICK_KEYS)[number], string>>;
}

export const UTM_KEYS = ["source", "medium", "campaign", "term", "content"] as const;
export const CLICK_KEYS = ["gclid", "gbraid", "wbraid", "fbclid", "msclkid"] as const;
/** The API's limits (leads/fields.py: Tag200, ClickId). */
const UTM_MAX = 200;
const CLICK_MAX = 500;
export const ATTRIBUTION_KEY = "empire.attribution";

/** UTM tags and click IDs from a landing address's query; anything else is ignored. */
export function attributionFromSearch(search: string): Attribution | null {
  const params = new URLSearchParams(search);
  const utm: Attribution["utm"] = {};
  const clickIds: Attribution["click_ids"] = {};
  for (const key of UTM_KEYS) {
    const value = params.get(`utm_${key}`)?.trim();
    if (value) utm[key] = value.slice(0, UTM_MAX);
  }
  for (const key of CLICK_KEYS) {
    const value = params.get(key)?.trim();
    if (value) clickIds[key] = value.slice(0, CLICK_MAX);
  }
  if (Object.keys(utm).length === 0 && Object.keys(clickIds).length === 0) return null;
  return { utm, click_ids: clickIds };
}

/**
 * First touch for the session: the first landing that carried tags wins, later pages keep it.
 * `stored` is what session storage holds (may be null or rubbish).
 */
export function mergeAttribution(stored: string | null, fresh: Attribution | null): Attribution {
  const empty: Attribution = { utm: {}, click_ids: {} };
  if (stored) {
    try {
      const parsed = JSON.parse(stored) as Attribution;
      if (parsed && typeof parsed === "object" && parsed.utm && parsed.click_ids) {
        // Re-filter what was stored, so a hand-edited value can't add other keys.
        const again = attributionFromSearch(
          new URLSearchParams([
            ...Object.entries(parsed.utm).map(([k, v]) => [`utm_${k}`, String(v)]),
            ...Object.entries(parsed.click_ids).map(([k, v]) => [k, String(v)]),
          ]).toString(),
        );
        if (again) return again;
      }
    } catch {
      // Unreadable storage: fall through to the fresh tags.
    }
  }
  return fresh ?? empty;
}

/** The referrer only when it is a web address (the API refuses anything else). */
export function cleanReferrer(referrer: string | null | undefined): string | null {
  if (!referrer) return null;
  try {
    const url = new URL(referrer);
    if (url.protocol !== "https:" && url.protocol !== "http:") return null;
    // WHY drop the query and fragment: another site's address can carry personal data too.
    return `${url.origin}${url.pathname}`.slice(0, 1000);
  } catch {
    return null;
  }
}

/** The path of the page the form is on, without query or fragment. */
export function pagePath(pathname: string): string {
  // "//foo" would read as another host to the API's address check; one slash is our path.
  return pathname.startsWith("/") ? pathname.replace(/^\/+/, "/").slice(0, 1000) : "/";
}

/**
 * Keeps this landing's tags for the tab (first touch). Called on every page view by
 * `AttributionCapture` in the site layout, and again just before a form is sent.
 */
export function captureAttribution(search: string, storage: Storage | null): Attribution {
  let stored: string | null = null;
  try {
    stored = storage?.getItem(ATTRIBUTION_KEY) ?? null;
  } catch {
    // Storage blocked (private mode, settings): use what this address carries.
  }
  const merged = mergeAttribution(stored, attributionFromSearch(search));
  try {
    if (Object.keys(merged.utm).length || Object.keys(merged.click_ids).length) {
      storage?.setItem(ATTRIBUTION_KEY, JSON.stringify(merged));
    }
  } catch {
    // Not stored; nothing else depends on it.
  }
  return merged;
}

const SOURCE: Record<LeadIntent, "project_form" | "contact_form" | "site_visit" | "brochure"> = {
  enquiry: "project_form",
  visit: "site_visit",
  brochure: "brochure",
};

/** The request body for the intent's endpoint (schemas_public.py). */
export function leadBody(
  intent: LeadIntent,
  input: LeadInput,
  context: { pathname: string; referrer?: string | null; attribution: Attribution },
): Record<string, unknown> {
  const body: Record<string, unknown> = {
    name: input.name.trim(),
    phone: input.phone.trim(),
    email: input.email?.trim() || null,
    message: input.message?.trim() || null,
    project_slug: input.projectSlug || null,
    configuration_id: input.configurationId || null,
    source:
      input.source ??
      (intent === "enquiry" && !input.projectSlug ? "contact_form" : SOURCE[intent]),
    page_url: pagePath(context.pathname),
    referrer: cleanReferrer(context.referrer),
    utm: context.attribution.utm,
    click_ids: context.attribution.click_ids,
    consent: { accepted: true, consent_text_id: input.consent.id, version: input.consent.version },
    // COMPLIANCE: only when ticked, and only with the text that was on screen.
    marketing_consent:
      input.marketingTicked && input.marketing
        ? {
            accepted: true,
            consent_text_id: input.marketing.id,
            version: input.marketing.version,
          }
        : null,
    website: input.website,
  };
  if (intent === "visit") {
    body.preferred_date = input.preferredDate;
    body.preferred_slot = input.preferredSlot;
  }
  return body;
}

export const ENDPOINT: Record<LeadIntent, string> = {
  enquiry: "/api/v1/public/leads",
  visit: "/api/v1/public/site-visits",
  brochure: "/api/v1/public/brochure-requests",
};

/** What the form shows after an answer. */
export type Outcome =
  | { kind: "ok"; reference: string; message: string; brochureUrl?: string }
  | { kind: "fields"; fields: Record<string, string>; message: string }
  | { kind: "reload"; message: string }
  | { kind: "error"; message: string };

interface ProblemLike {
  title?: string;
  detail?: string;
  errors?: { field?: string; message?: string }[];
}

/**
 * `shownFields`: the API field names this form draws, so a field error is put under its field;
 * an error about a field that isn't on screen (e.g. `project_slug` on a project page) is shown
 * at the top with the API's own words instead of "check the highlighted fields".
 */
export function outcomeFor(
  status: number,
  body: unknown,
  shownFields: ReadonlySet<string> = new Set(),
): Outcome {
  const data = (body && typeof body === "object" ? body : {}) as ProblemLike & {
    reference?: string;
    message?: string;
    url?: string;
  };
  if (status === 201 && data.reference) {
    return {
      kind: "ok",
      reference: data.reference,
      message: data.message ?? "Thank you. Our team will call you back.",
      brochureUrl: data.url,
    };
  }
  if (status === 409) {
    return {
      kind: "reload",
      message:
        "The consent wording has just been updated. Please reload the page to see it; what you typed stays here until you do.",
    };
  }
  if (status === 422) {
    const fields: Record<string, string> = {};
    let elsewhere: string | undefined;
    for (const e of data.errors ?? []) {
      const field = (e.field ?? "").split(".").pop() ?? "";
      if (shownFields.has(field) && e.message) {
        if (!fields[field]) fields[field] = e.message;
      } else if (!elsewhere && e.message) {
        elsewhere = e.message;
      }
    }
    return {
      kind: "fields",
      fields,
      message:
        elsewhere ??
        (Object.keys(fields).length > 0
          ? "Please check the highlighted fields."
          : (data.detail ?? "Please check your details and try again.")),
    };
  }
  if (status === 429) {
    return {
      kind: "error",
      message: "Too many tries from this network or number. Please wait a few minutes, or call us.",
    };
  }
  if (status === 503) {
    return {
      kind: "error",
      message: "Enquiries from the website aren't open yet. Please call or WhatsApp us.",
    };
  }
  if (status === 404) {
    return { kind: "error", message: "This project isn't available any more. Please call us." };
  }
  return {
    kind: "error",
    message: "We couldn't send this. Please try again, or call or WhatsApp us.",
  };
}

/**
 * Checks done before sending, with plain messages (the API's own would be technical for some
 * fields). Returns field → message; empty means the form may be sent.
 */
export function checkBeforeSend(
  intent: LeadIntent,
  values: { name: string; phone: string; projectSlug?: string | null; preferredDate?: string },
  needsProject: boolean,
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (values.name.trim().length < 2) errors.name = "Please enter your name.";
  if (!values.phone.trim()) errors.phone = "Please enter your mobile number.";
  if (needsProject && !values.projectSlug) errors.project_slug = "Please choose a project.";
  if (intent === "visit" && !values.preferredDate) {
    errors.preferred_date = "Please choose a day for the visit.";
  }
  return errors;
}

/** The message when the request never reached us (offline, DNS, timeout). */
export const OFFLINE_MESSAGE =
  "You seem to be offline. Check your connection and try again; what you typed is kept.";

/** The earliest and latest visit days the API accepts (today … +120 days, India time). */
export function visitDateRange(now: Date = new Date()): { min: string; max: string } {
  const ist = (d: Date) => new Date(d.getTime() + 330 * 60_000).toISOString().slice(0, 10);
  return { min: ist(now), max: ist(new Date(now.getTime() + 120 * 86_400_000)) };
}
