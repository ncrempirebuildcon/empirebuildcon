/**
 * Configuration form data: the draft the editor's form edits, and the conversion from the API's
 * Configuration and to its ConfigurationInput.
 *
 * COMPLIANCE: area is typed in sq ft and sent once, in square metres (ARCHITECTURE §6), using the
 * shared helpers; the sq m shown next to it is derived the same way, so the figures never disagree.
 */
import { sqftToSqm, sqftToSqmStored, sqmToSqft } from "@empire/ui";
import type { Schema } from "@/lib/api";
import type { AreaBasis, AreaUnit, PropertyType, SalesStatus } from "@/lib/labels";
import type { Configuration } from "./editorTypes";

export interface ConfigurationDraft {
  name: string;
  slug: string;
  tower_id: string;
  property_type: PropertyType;
  bhk: number | null;
  bathrooms: number | null;
  balconies: number | null;
  basis: AreaBasis;
  display_unit: AreaUnit;
  area_min_sqft: number | null;
  area_max_sqft: number | null;
  price_on_request: boolean;
  price_min_inr: number | null;
  price_max_inr: number | null;
  sales_status: SalesStatus;
  /** Price fields the CMS does not edit yet, kept as they are. */
  keep: Pick<Schema<"Price">, "rate_inr" | "rate_unit" | "note">;
}

export const emptyDraft = (): ConfigurationDraft => ({
  name: "",
  slug: "",
  tower_id: "",
  property_type: "apartment",
  bhk: null,
  bathrooms: null,
  balconies: null,
  basis: "carpet",
  display_unit: "sqft",
  area_min_sqft: null,
  area_max_sqft: null,
  price_on_request: false,
  price_min_inr: null,
  price_max_inr: null,
  sales_status: "available",
  keep: { rate_inr: null, rate_unit: null, note: null },
});

const sqftOf = (sqm: number | null | undefined) => (sqm == null ? null : sqmToSqft(sqm));

export const toDraft = (c: Configuration): ConfigurationDraft => ({
  name: c.name,
  slug: c.slug,
  tower_id: c.tower_id ?? "",
  property_type: c.property_type,
  bhk: c.bhk ?? null,
  bathrooms: c.bathrooms ?? null,
  balconies: c.balconies ?? null,
  basis: c.area.basis ?? "carpet",
  display_unit: c.area.display_unit ?? "sqft",
  area_min_sqft: sqftOf(c.area.min_sqm),
  area_max_sqft: sqftOf(c.area.max_sqm),
  price_on_request: c.price.on_request ?? false,
  price_min_inr: c.price.min_inr ?? null,
  price_max_inr: c.price.max_inr ?? null,
  sales_status: c.sales_status,
  keep: {
    rate_inr: c.price.rate_inr ?? null,
    rate_unit: c.price.rate_unit ?? null,
    note: c.price.note ?? null,
  },
});

export const toInput = (d: ConfigurationDraft): Schema<"ConfigurationInput"> => ({
  name: d.name.trim(),
  ...(d.slug.trim() ? { slug: d.slug.trim() } : {}),
  tower_id: d.tower_id || null,
  property_type: d.property_type,
  bhk: d.bhk,
  bathrooms: d.bathrooms,
  balconies: d.balconies,
  area: {
    // WHY: `display` is read-only and ignored by the API; the generated type still lists it.
    display: "",
    basis: d.basis,
    display_unit: d.display_unit,
    // WHY: stored once in square metres, with 4 decimals so it reads back as the same sq ft.
    min_sqm: d.area_min_sqft === null ? null : sqftToSqmStored(d.area_min_sqft),
    max_sqm: d.area_max_sqft === null ? null : sqftToSqmStored(d.area_max_sqft),
  },
  price: {
    display: "",
    on_request: d.price_on_request,
    min_inr: d.price_min_inr,
    max_inr: d.price_max_inr,
    ...d.keep,
  },
  sales_status: d.sales_status,
});

export function validate(d: ConfigurationDraft) {
  const errors: Record<string, string> = {};
  if (!d.name.trim()) errors.name = "Enter a name, e.g. 2 BHK Classic.";
  if (d.area_min_sqft !== null && d.area_max_sqft !== null && d.area_min_sqft > d.area_max_sqft) {
    errors["area.max_sqm"] = "Area up to must be the same as or more than area from.";
  }
  if (d.price_min_inr !== null && d.price_max_inr !== null && d.price_min_inr > d.price_max_inr) {
    errors["price.max_inr"] = "Price up to must be the same as or more than price from.";
  }
  if (d.slug.trim() && !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(d.slug.trim())) {
    errors.slug = "Use lowercase letters, numbers and single hyphens.";
  }
  return errors;
}

/** "980" or "980 – 1,050" in sq ft from stored square metres. */
export function sqftRange(min: number | null | undefined, max: number | null | undefined): string {
  const group = new Intl.NumberFormat("en-IN");
  if (min == null) return "—";
  const lo = group.format(sqmToSqft(min));
  return max == null || sqmToSqft(max) === sqmToSqft(min)
    ? lo
    : `${lo} – ${group.format(sqmToSqft(max))}`;
}

/** The same in sq m, one decimal, derived from the sq ft figures shown next to it. */
export function sqmRange(min: number | null | undefined, max: number | null | undefined): string {
  if (min == null) return "—";
  const lo = sqftToSqm(sqmToSqft(min)).toFixed(1);
  if (max == null || sqmToSqft(max) === sqmToSqft(min)) return lo;
  return `${lo} – ${sqftToSqm(sqmToSqft(max)).toFixed(1)}`;
}
