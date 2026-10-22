/**
 * The project editor's own fields (everything saved by the one "Save draft" button), and the
 * conversion between the API's ProjectAdmin and the form, and from the form to the PATCH body
 * (ProjectUpdate).
 *
 * WHY a flat form: inputs work with strings ("" for empty) and the API with nulls and nested
 * objects; converting in one place keeps every field's empty value consistent.
 *
 * Child lists (towers, configurations, …) are not here: each item saves through its own endpoint.
 */
import type { Schema } from "@/lib/api";
import type { AreaUnit, ProjectStatus, ProjectType, SalesStatus } from "@/lib/labels";

export type ProjectAdmin = Schema<"ProjectAdmin">;
/** The PATCH body: every field optional (the API's ProjectUpdate). */
export type ProjectUpdate = Schema<"ProjectUpdate">;

export interface ProjectForm {
  name: string;
  slug: string;
  tagline: string;
  description: string;
  status: ProjectStatus;
  sales_status: SalesStatus;
  project_type: ProjectType;
  is_featured: boolean;
  featured_order: number | null;
  launch_date: string;
  rera_authority: string;
  rera_number: string;
  rera_url: string;
  possession_date: string;
  rera_bank_name: string;
  rera_account_name: string;
  rera_account_number: string;
  price_on_request: boolean;
  price_min_inr: number | null;
  price_max_inr: number | null;
  rate_inr: number | null;
  rate_unit: AreaUnit | "";
  price_note: string;
  city_id: string;
  locality_id: string;
  address_line: string;
  state: string;
  pincode: string;
  lat: number | null;
  lng: number | null;
  google_maps_url: string;
  plus_code: string;
  pin_source: "url" | "plus_code" | "manual" | "";
  seo_title: string;
  seo_description: string;
  seo_canonical_path: string;
  seo_noindex: boolean;
}

export const DEFAULT_RERA_AUTHORITY = "UP-RERA";
export const DEFAULT_STATE = "Uttar Pradesh";

const text = (value: string | null | undefined) => value ?? "";
const orNull = (value: string) => (value.trim() === "" ? null : value.trim());

export function toForm(p: ProjectAdmin): ProjectForm {
  const location = p.location;
  return {
    name: p.name,
    slug: p.slug,
    tagline: text(p.tagline),
    description: text(p.description),
    status: p.status,
    sales_status: p.sales_status,
    project_type: p.project_type ?? "residential",
    is_featured: p.is_featured ?? false,
    featured_order: p.featured_order ?? null,
    launch_date: text(p.launch_date),
    rera_authority: p.rera.authority ?? DEFAULT_RERA_AUTHORITY,
    rera_number: text(p.rera.number),
    rera_url: text(p.rera.url),
    possession_date: text(p.possession_date),
    rera_bank_name: text(p.rera_account?.bank_name),
    rera_account_name: text(p.rera_account?.account_name),
    rera_account_number: text(p.rera_account?.account_number),
    price_on_request: p.price.on_request ?? false,
    price_min_inr: p.price.min_inr ?? null,
    price_max_inr: p.price.max_inr ?? null,
    rate_inr: p.price.rate_inr ?? null,
    rate_unit: p.price.rate_unit ?? "",
    price_note: text(p.price.note),
    city_id: location?.city?.id ?? "",
    locality_id: location?.locality?.id ?? "",
    address_line: text(location?.address_line),
    state: location?.state ?? DEFAULT_STATE,
    pincode: text(location?.pincode),
    lat: location?.lat ?? null,
    lng: location?.lng ?? null,
    google_maps_url: text(location?.google_maps_url),
    plus_code: text(location?.plus_code),
    pin_source: location?.pin_source ?? "",
    seo_title: text(p.seo?.title),
    seo_description: text(p.seo?.description),
    seo_canonical_path: text(p.seo?.canonical_path),
    seo_noindex: p.seo?.noindex ?? false,
  };
}

/**
 * The PATCH body for the form. Only fields the editor owns are sent, so values edited elsewhere
 * (translations, land area, the share image) are left as they are.
 */
export function toInput(form: ProjectForm, project: ProjectAdmin): ProjectUpdate {
  const hasAccount = Boolean(
    form.rera_bank_name.trim() || form.rera_account_name.trim() || form.rera_account_number.trim(),
  );
  return {
    name: form.name.trim(),
    ...(form.slug.trim() ? { slug: form.slug.trim() } : {}),
    tagline: orNull(form.tagline),
    description: orNull(form.description),
    status: form.status,
    sales_status: form.sales_status,
    project_type: form.project_type,
    is_featured: form.is_featured,
    featured_order: form.is_featured ? form.featured_order : null,
    launch_date: orNull(form.launch_date),
    rera_authority: form.rera_authority.trim() || DEFAULT_RERA_AUTHORITY,
    rera_number: orNull(form.rera_number),
    rera_url: orNull(form.rera_url),
    possession_date: orNull(form.possession_date),
    rera_account: hasAccount
      ? {
          bank_name: orNull(form.rera_bank_name),
          account_name: orNull(form.rera_account_name),
          account_number: orNull(form.rera_account_number),
        }
      : null,
    price: {
      // WHY: `display` is read-only and ignored by the API; the generated type still lists it.
      display: "",
      on_request: form.price_on_request,
      min_inr: form.price_min_inr,
      max_inr: form.price_max_inr,
      rate_inr: form.rate_inr,
      rate_unit: form.rate_inr === null ? null : form.rate_unit || "sqft",
      note: orNull(form.price_note),
    },
    location: {
      address_line: orNull(form.address_line),
      city_id: form.city_id || null,
      locality_id: form.locality_id || null,
      state: form.state.trim() || DEFAULT_STATE,
      pincode: orNull(form.pincode),
      lat: form.lat,
      lng: form.lng,
      google_maps_url: orNull(form.google_maps_url),
      plus_code: orNull(form.plus_code),
      pin_source: form.lat === null || form.lng === null ? null : form.pin_source || "manual",
    },
    seo: {
      title: orNull(form.seo_title),
      description: orNull(form.seo_description),
      canonical_path: orNull(form.seo_canonical_path),
      noindex: form.seo_noindex,
      og_image_id: project.seo?.og_image_id ?? null,
    },
  };
}

/** Which editor tab shows a field, so an error summary can send the user to the right place. */
export function tabForField(field: string): string {
  if (field.startsWith("location.")) return "location";
  if (field.startsWith("seo.")) return "seo";
  if (field.startsWith("rera_account")) return "documents";
  return "details";
}

/** Human names for field paths in the error summary. */
export const FIELD_LABELS: Record<string, string> = {
  name: "Project name",
  slug: "Web address",
  tagline: "Tagline",
  description: "Short description",
  status: "Construction status",
  sales_status: "Sales status",
  project_type: "Project type",
  featured_order: "Featured order",
  launch_date: "Launch date",
  rera_authority: "RERA authority",
  rera_number: "RERA registration number",
  rera_url: "RERA page link",
  possession_date: "Possession date",
  "rera_account.bank_name": "Bank",
  "rera_account.account_name": "Account name",
  "rera_account.account_number": "Account number",
  "price.min_inr": "Price from",
  "price.max_inr": "Price up to",
  "price.rate_inr": "Rate",
  "price.rate_unit": "Rate unit",
  "price.note": "Price note",
  price: "Price",
  "location.city_id": "City",
  "location.locality_id": "Locality",
  "location.address_line": "Address",
  "location.state": "State",
  "location.pincode": "PIN code",
  "location.lat": "Latitude",
  "location.lng": "Longitude",
  "location.google_maps_url": "Google Maps link",
  "location.plus_code": "Plus code",
  "seo.title": "Search title",
  "seo.description": "Search description",
  "seo.canonical_path": "Canonical path",
};

/** Checks made before saving, so obvious mistakes show without a round trip. */
export function validateForm(form: ProjectForm): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!form.name.trim()) errors.name = "Enter the project's name.";
  if (form.slug.trim() && !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(form.slug.trim())) {
    errors.slug = "Use lowercase letters, numbers and single hyphens, e.g. aurum-heights.";
  }
  if (
    form.price_min_inr !== null &&
    form.price_max_inr !== null &&
    form.price_min_inr > form.price_max_inr
  ) {
    errors["price.max_inr"] = "Price up to must be the same as or more than price from.";
  }
  if (form.pincode.trim() && !/^[1-9][0-9]{5}$/.test(form.pincode.trim())) {
    errors["location.pincode"] = "A PIN code has 6 digits and doesn't start with 0.";
  }
  if (form.lat !== null && (form.lat < -90 || form.lat > 90)) {
    errors["location.lat"] = "Latitude is between -90 and 90.";
  }
  if (form.lng !== null && (form.lng < -180 || form.lng > 180)) {
    errors["location.lng"] = "Longitude is between -180 and 180.";
  }
  if ((form.lat === null) !== (form.lng === null)) {
    errors[form.lat === null ? "location.lat" : "location.lng"] =
      "Enter both latitude and longitude, or neither.";
  }
  if (form.seo_canonical_path.trim() && !form.seo_canonical_path.trim().startsWith("/")) {
    errors["seo.canonical_path"] = "Start the path with /, e.g. /projects/aurum-heights.";
  }
  return errors;
}

/**
 * The form after a save: each field still equal to what was sent takes the saved value (the API
 * may tidy it, e.g. trim text or make the slug); a field changed while the save ran keeps the
 * user's newer value.
 */
export function mergeAfterSave(
  current: ProjectForm,
  sent: ProjectForm,
  saved: ProjectForm,
): ProjectForm {
  const merged = { ...saved };
  for (const key of Object.keys(current) as Array<keyof ProjectForm>) {
    if (current[key] !== sent[key]) Object.assign(merged, { [key]: current[key] });
  }
  return merged;
}

/** True when two forms hold the same values (for the unsaved-changes warning). */
export function sameForm(a: ProjectForm, b: ProjectForm): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}
