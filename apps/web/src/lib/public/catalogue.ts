/**
 * Project and property catalogue helpers for the public site (task 5.3, D-041).
 *
 * - Reads the filters of /projects, /properties and /cities/<slug> from the URL and turns them
 *   into the 5.1 API's query, dropping anything the API would refuse (bad slug, unknown sort,
 *   negative budget). A visitor who edits the URL by hand gets the nearest valid list, never
 *   an error page.
 * - Builds filter and page links that keep the other parameters, so the filter form works as a
 *   plain GET form without JavaScript.
 * - Public paths for projects, properties and cities, the same ones the API's sitemap feed
 *   and redirects use (apps/api/src/empire_api/seo/paths.py). Keep the two in step.
 *
 * WHY budget presets instead of free numbers: the boards show three bands. The bands send whole
 * rupees to the API (`budget_min`/`budget_max`), which compares them with the stored price
 * range. A project with "price on request" has no numbers, so a budget filter leaves it out.
 */

export const PROJECT_STATUS_LABEL: Record<string, string> = {
  upcoming: "Upcoming",
  ongoing: "Under construction",
  completed: "Ready to move",
};

export const SALES_STATUS_LABEL: Record<string, string> = {
  available: "Available",
  sold_out: "Sold out",
};

export const PROJECT_SORTS = [
  { value: "recommended", label: "Recommended" },
  { value: "price_asc", label: "Price: low to high" },
  { value: "price_desc", label: "Price: high to low" },
  { value: "possession", label: "Possession: soonest" },
  { value: "newest", label: "Newest" },
] as const;

export const PROPERTY_SORTS = [
  { value: "recommended", label: "Recommended" },
  { value: "price_asc", label: "Price: low to high" },
  { value: "price_desc", label: "Price: high to low" },
  { value: "size_desc", label: "Carpet area: largest first" },
] as const;

const LAKH = 1_00_000;
const CRORE = 1_00_00_000;

/** Budget bands from the boards, in whole rupees. */
export const BUDGETS = [
  { value: "under-75l", label: "Up to ₹ 75 L", max: 75 * LAKH },
  { value: "75l-1.5cr", label: "₹ 75 L – ₹ 1.5 Cr", min: 75 * LAKH, max: 1.5 * CRORE },
  { value: "above-1.5cr", label: "Above ₹ 1.5 Cr", min: 1.5 * CRORE },
] as const;

export const BHKS = [
  { value: "1", label: "1 BHK" },
  { value: "2", label: "2 BHK" },
  { value: "3", label: "3 BHK" },
  { value: "4", label: "4 BHK" },
] as const;

export const PROPERTY_TYPES = [
  { value: "apartment", label: "Apartments" },
  { value: "villa", label: "Villas" },
  { value: "plot", label: "Plots" },
  { value: "penthouse", label: "Penthouses" },
] as const;

const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const MAX_QUERY = 200;
export const PER_PAGE = 12;

export type SearchParams = Record<string, string | string[] | undefined>;

/** The filters a list page understands, already checked. Empty values are left out. */
export interface CatalogueFilters {
  q?: string;
  status?: "upcoming" | "ongoing" | "completed";
  city?: string;
  locality?: string;
  type?: string;
  bhk?: string;
  budget?: (typeof BUDGETS)[number]["value"];
  sort?: string;
  page: number;
}

function first(value: string | string[] | undefined): string | undefined {
  const v = Array.isArray(value) ? value[0] : value;
  const trimmed = v?.trim();
  return trimmed ? trimmed : undefined;
}

function oneOf<T extends string>(value: string | undefined, allowed: readonly T[]): T | undefined {
  return value !== undefined && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : undefined;
}

/** Reads and checks the filters. `sorts` is the sort list of the page (projects or properties). */
export function parseFilters(
  params: SearchParams,
  sorts: readonly { value: string }[] = PROJECT_SORTS,
): CatalogueFilters {
  const q = first(params.q)?.slice(0, MAX_QUERY);
  const city = first(params.city);
  const locality = first(params.locality);
  const page = Number.parseInt(first(params.page) ?? "1", 10);
  return {
    q,
    status: oneOf(first(params.status), ["upcoming", "ongoing", "completed"] as const),
    city: city && SLUG.test(city) && city.length <= 120 ? city : undefined,
    locality: locality && SLUG.test(locality) && locality.length <= 120 ? locality : undefined,
    type: oneOf(
      first(params.type),
      PROPERTY_TYPES.map((t) => t.value),
    ),
    bhk: oneOf(
      first(params.bhk),
      BHKS.map((b) => b.value),
    ),
    budget: oneOf(
      first(params.budget),
      BUDGETS.map((b) => b.value),
    ),
    sort: oneOf(
      first(params.sort),
      sorts.map((s) => s.value),
    ),
    page: Number.isFinite(page) && page >= 1 && page <= 1000 ? page : 1,
  };
}

/** The API query for /public/projects. */
export function projectQuery(f: CatalogueFilters) {
  const band = BUDGETS.find((b) => b.value === f.budget);
  return {
    q: f.q,
    status: f.status,
    city: f.city,
    locality: f.locality,
    type: f.type,
    bhk: f.bhk ? Number(f.bhk) : undefined,
    budget_min: band && "min" in band ? band.min : undefined,
    budget_max: band && "max" in band ? band.max : undefined,
    sort: f.sort as
      "recommended" | "price_asc" | "price_desc" | "possession" | "newest" | undefined,
    page: f.page,
    per_page: PER_PAGE,
  };
}

/** The API query for /public/properties (no text search; the project's status is a filter). */
export function propertyQuery(f: CatalogueFilters) {
  const band = BUDGETS.find((b) => b.value === f.budget);
  return {
    city: f.city,
    locality: f.locality,
    type: f.type,
    bhk: f.bhk ? Number(f.bhk) : undefined,
    budget_min: band && "min" in band ? band.min : undefined,
    budget_max: band && "max" in band ? band.max : undefined,
    project_status: f.status,
    sort: f.sort as "recommended" | "price_asc" | "price_desc" | "size_desc" | undefined,
    page: f.page,
    per_page: PER_PAGE,
  };
}

/** True when any filter (not the page or the sort) is set. */
export function hasFilters(f: CatalogueFilters): boolean {
  return Boolean(f.q || f.status || f.city || f.locality || f.type || f.bhk || f.budget);
}

/**
 * A link to `path` with the current filters and `changes` applied. A change of any filter goes
 * back to page 1; `undefined` or "" removes a parameter. Parameters keep a fixed order so the
 * same list always has the same address (one cache entry, one canonical URL later in 5.6).
 */
export function filterHref(
  path: string,
  f: CatalogueFilters,
  changes: Partial<Record<keyof CatalogueFilters, string | number | undefined>> = {},
): string {
  const order: (keyof CatalogueFilters)[] = [
    "q",
    "status",
    "city",
    "locality",
    "type",
    "bhk",
    "budget",
    "sort",
    "page",
  ];
  const merged: Record<string, string | number | undefined> = { ...f, ...changes };
  const onlyPage = Object.keys(changes).every((k) => k === "page");
  if (!onlyPage) merged.page = changes.page;
  const params = new URLSearchParams();
  for (const key of order) {
    const value = merged[key];
    if (value === undefined || value === "") continue;
    if (key === "page" && Number(value) <= 1) continue;
    params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

// --- Public paths (D-041; the API twin is seo/paths.py) ----------------------------------------

export function projectPath(slug: string): string {
  return `/projects/${slug}`;
}

export function propertyPath(projectSlug: string, configSlug: string): string {
  return `/projects/${projectSlug}/${configSlug}`;
}

export function cityPath(slug: string): string {
  return `/cities/${slug}`;
}

// --- Display helpers ---------------------------------------------------------------------------

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** "June 2029" for a calendar date ("2029-06-30"); RERA possession dates are shown by month. */
export function formatMonthYear(isoDate: string | null | undefined): string | null {
  if (!isoDate) return null;
  const match = /^(\d{4})-(\d{2})/.exec(isoDate);
  if (!match) return null;
  const month = Number(match[2]);
  if (month < 1 || month > 12) return null;
  return `${MONTHS[month - 1]} ${match[1]}`;
}

/** "3 BHK", "2.5 BHK"; null when the configuration has no BHK (a plot or a shop). */
export function bhkLabel(bhk: number | null | undefined): string | null {
  if (bhk === null || bhk === undefined || bhk <= 0) return null;
  return `${Number.isInteger(bhk) ? bhk : bhk.toFixed(1)} BHK`;
}

/** "≈ 1.8 km · 6 min" for a location advantage; parts that aren't set are left out. */
export function distanceLabel(
  km: number | null | undefined,
  minutes: number | null | undefined,
): string | null {
  const parts: string[] = [];
  if (km !== null && km !== undefined) {
    parts.push(`≈ ${km < 10 ? km.toFixed(1).replace(/\.0$/, "") : Math.round(km)} km`);
  }
  if (minutes !== null && minutes !== undefined) parts.push(`${minutes} min`);
  return parts.length ? parts.join(" · ") : null;
}

/** Page numbers to show around the current one: 1 … 4 5 6 … 12. `null` is a gap. */
export function pageWindow(current: number, total: number): (number | null)[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages = new Set([1, total, current - 1, current, current + 1]);
  const sorted = [...pages].filter((p) => p >= 1 && p <= total).sort((a, b) => a - b);
  const out: (number | null)[] = [];
  for (const p of sorted) {
    const last = out[out.length - 1];
    if (typeof last === "number" && p - last > 1) out.push(null);
    out.push(p);
  }
  return out;
}

/** Google Maps directions to the pin, or to the address when there is no pin. */
export function directionsUrl(location: {
  directions_url?: string | null;
  google_maps_url?: string | null;
  lat?: number | null;
  lng?: number | null;
  address_line?: string | null;
}): string | null {
  if (location.directions_url) return location.directions_url;
  if (
    location.lat !== null &&
    location.lat !== undefined &&
    location.lng !== null &&
    location.lng !== undefined
  ) {
    return `https://www.google.com/maps/dir/?api=1&destination=${location.lat},${location.lng}`;
  }
  return location.google_maps_url ?? null;
}
