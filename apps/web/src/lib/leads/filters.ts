/**
 * The lead inbox's filters, read from and written to the address bar, and turned into the query
 * of `GET /admin/leads` and `GET /admin/leads/export.csv` (ARCHITECTURE §8: "filters in the URL";
 * the dashboard's count links open the inbox with these same parameters).
 *
 * WHY the API's own parameter names in the address: the dashboard counts carry links the API
 * builds (`/admin/leads?status=new`), so the CMS reads exactly what the API writes, and the
 * export downloads exactly the list on screen.
 *
 * SECURITY: `q` can hold a mobile number (the search finds a phone by its last digits). It may
 * live in the address, but is never put into a page title, a heading or any log or report
 * (SECURITY.md §8); the inbox's title stays "Leads".
 */
import { LEAD_SOURCE, LEAD_STATUS, type LeadSource, type LeadStatus } from "./labels";
import { LEADS_PATH } from "../routes";
import { isCalendarDate } from "@empire/ui/format";

export type InboxView = "table" | "board";

export interface LeadFilters {
  q: string;
  status: LeadStatus | "";
  /** "", a project's id, or "none" for general enquiries (no project). */
  project_id: string;
  /** "", "me", "unassigned" or a user's id. */
  owner_id: string;
  source: LeadSource | "";
  /** Campaign tags (exact), e.g. from a UTM report row: `utm_source`, `utm_medium`, `utm_campaign`. */
  utm_source: string;
  utm_medium: string;
  utm_campaign: string;
  /** "true": still being worked (not booked, lost or erased); "false": the rest; "": all. */
  open: "" | "true" | "false";
  /** Received on or after, a calendar date in India ("2026-10-01"). */
  from: string;
  /** Received on or before. */
  to: string;
  /** Only unread leads. */
  unread: boolean;
  /** Only leads marked as spam (spam is hidden otherwise). */
  spam: boolean;
  view: InboxView;
  page: number;
}

export const EMPTY_FILTERS: LeadFilters = {
  q: "",
  status: "",
  project_id: "",
  owner_id: "",
  source: "",
  utm_source: "",
  utm_medium: "",
  utm_campaign: "",
  open: "",
  from: "",
  to: "",
  unread: false,
  spam: false,
  view: "table",
  page: 1,
};

/** The project filter value for general enquiries (no project), as the API names it. */
export const GENERAL = "none";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function pick<K extends string>(labels: Record<K, string>, value: string | null): K | "" {
  return value && Object.hasOwn(labels, value) ? (value as K) : "";
}

/** The filters in an address; unknown or malformed values are dropped, never sent on. */
export function readLeadFilters(params: URLSearchParams): LeadFilters {
  const owner = params.get("owner_id") ?? "";
  const project = params.get("project_id") ?? "";
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";
  const page = Number.parseInt(params.get("page") ?? "1", 10);
  return {
    q: (params.get("q") ?? "").slice(0, 100),
    status: pick(LEAD_STATUS, params.get("status")),
    project_id: project === GENERAL || UUID_RE.test(project) ? project : "",
    owner_id: owner === "me" || owner === "unassigned" || UUID_RE.test(owner) ? owner : "",
    source: pick(LEAD_SOURCE, params.get("source")),
    utm_source: (params.get("utm_source") ?? "").slice(0, 200),
    utm_medium: (params.get("utm_medium") ?? "").slice(0, 200),
    utm_campaign: (params.get("utm_campaign") ?? "").slice(0, 200),
    open: params.get("open") === "true" ? "true" : params.get("open") === "false" ? "false" : "",
    from: isCalendarDate(from) ? from : "",
    to: isCalendarDate(to) ? to : "",
    unread: params.get("read") === "false",
    spam: params.get("is_spam") === "true",
    view: params.get("view") === "board" ? "board" : "table",
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

/** True when anything narrows the list (the view and the page don't count). */
export function hasLeadFilters(filters: LeadFilters): boolean {
  return Boolean(
    filters.q ||
    filters.status ||
    filters.project_id ||
    filters.owner_id ||
    filters.source ||
    filters.utm_source ||
    filters.utm_medium ||
    filters.utm_campaign ||
    filters.open ||
    filters.from ||
    filters.to ||
    filters.unread ||
    filters.spam,
  );
}

/** The search part of an address or API call for these filters (defaults left out). */
function filterParams(filters: LeadFilters): URLSearchParams {
  const search = new URLSearchParams();
  if (filters.q) search.set("q", filters.q);
  if (filters.status) search.set("status", filters.status);
  if (filters.project_id) search.set("project_id", filters.project_id);
  if (filters.owner_id) search.set("owner_id", filters.owner_id);
  if (filters.source) search.set("source", filters.source);
  if (filters.utm_source) search.set("utm_source", filters.utm_source);
  if (filters.utm_medium) search.set("utm_medium", filters.utm_medium);
  if (filters.utm_campaign) search.set("utm_campaign", filters.utm_campaign);
  if (filters.open) search.set("open", filters.open);
  if (filters.from) search.set("from", filters.from);
  if (filters.to) search.set("to", filters.to);
  if (filters.unread) search.set("read", "false");
  if (filters.spam) search.set("is_spam", "true");
  return search;
}

/** The inbox address for some filters. */
export function leadsHref(filters: LeadFilters): string {
  const search = filterParams(filters);
  if (filters.view === "board") search.set("view", "board");
  if (filters.page > 1) search.set("page", String(filters.page));
  const query = search.toString();
  return query ? `${LEADS_PATH}?${query}` : LEADS_PATH;
}

/** The CSV export address for the list on screen (same filters, every page). */
export function exportHref(filters: LeadFilters): string {
  const query = filterParams(filters).toString();
  return `/api/v1/admin/leads/export.csv${query ? `?${query}` : ""}`;
}

/** The query for `GET /admin/leads`. */
export function leadsQuery(filters: LeadFilters, page: number, perPage: number) {
  return {
    page,
    per_page: perPage,
    q: filters.q || undefined,
    status: filters.status || undefined,
    project_id: filters.project_id || undefined,
    owner_id: filters.owner_id || undefined,
    source: filters.source || undefined,
    utm_source: filters.utm_source || undefined,
    utm_medium: filters.utm_medium || undefined,
    utm_campaign: filters.utm_campaign || undefined,
    open: filters.open ? filters.open === "true" : undefined,
    from: filters.from || undefined,
    to: filters.to || undefined,
    read: filters.unread ? false : undefined,
    is_spam: filters.spam ? true : undefined,
  };
}
