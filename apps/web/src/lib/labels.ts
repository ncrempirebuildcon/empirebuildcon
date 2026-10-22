/**
 * Words the CMS shows for the API's enum values, in the design boards' wording
 * (NoirCmsProject: "Under construction", "Sold out (shown last, with a badge)", …).
 *
 * Keys are typed from the generated client, so a new or renamed enum value fails the type-check
 * here instead of showing a raw key on screen.
 */
import type { ChipVariant, SelectOption } from "@empire/ui";
import type { Schema } from "./api";

type Labels<K extends string> = Record<K, string>;

export type ProjectStatus = Schema<"ProjectAdmin">["status"];
export type SalesStatus = Schema<"ProjectAdmin">["sales_status"];
export type PublishState = Schema<"ProjectAdmin">["publish_state"];
export type ProjectType = Schema<"ProjectAdmin">["project_type"];
export type TowerKind = Schema<"Tower">["kind"];
export type TowerStatus = Schema<"Tower">["status"];
export type PropertyType = Schema<"Configuration">["property_type"];
export type AreaBasis = NonNullable<Schema<"Area">["basis"]>;
export type AreaUnit = NonNullable<Schema<"Area">["display_unit"]>;
export type AdvantageKind = Schema<"LocationAdvantage">["kind"];
export type AmenityCategory = Schema<"Amenity">["category"];
export type UpdateState = NonNullable<Schema<"ConstructionUpdate">["publish_state"]>;

export const ROLE_LABELS: Record<string, string> = {
  super_admin: "Super-admin",
  admin: "Admin",
  sales: "Sales",
  marketing: "Marketing",
  content_editor: "Content editor",
};

/** Construction status. The API calls it `status`; the boards call it "Construction status". */
export const PROJECT_STATUS: Labels<ProjectStatus> = {
  upcoming: "Upcoming",
  ongoing: "Under construction",
  completed: "Ready to move",
};

export const PROJECT_STATUS_CHIP: Record<ProjectStatus, ChipVariant> = {
  upcoming: "upcoming",
  ongoing: "ongoing",
  completed: "completed",
};

export const SALES_STATUS: Labels<SalesStatus> = {
  available: "Available",
  sold_out: "Sold out",
  off_market: "Off market",
};

/** Sales status choices with the board's helper text (NoirCmsProject, Details tab). */
export const SALES_STATUS_HELP: Labels<SalesStatus> = {
  available: "Available",
  sold_out: "Sold out (shown last, with a badge)",
  off_market: "Off market (hidden from the website)",
};

export const SALES_STATUS_CHIP: Record<SalesStatus, ChipVariant> = {
  available: "available",
  sold_out: "soldOut",
  off_market: "offMarket",
};

export const PUBLISH_STATE: Labels<PublishState> = {
  draft: "Draft",
  published: "Published",
  archived: "Archived",
};

export const PUBLISH_STATE_CHIP: Record<PublishState, ChipVariant> = {
  draft: "draft",
  published: "published",
  archived: "archived",
};

export const PROJECT_TYPE: Labels<ProjectType> = {
  residential: "Residential",
  commercial: "Commercial",
  mixed: "Mixed use",
  plots: "Plots",
};

export const TOWER_KIND: Labels<TowerKind> = {
  tower: "Tower",
  phase: "Phase",
  block: "Block",
  wing: "Wing",
};

export const TOWER_STATUS: Labels<TowerStatus> = {
  planned: "Planned",
  under_construction: "Under construction",
  completed: "Completed",
};

export const PROPERTY_TYPE: Labels<PropertyType> = {
  apartment: "Apartment",
  villa: "Villa",
  plot: "Plot",
  penthouse: "Penthouse",
  shop: "Shop",
  office: "Office",
  other: "Other",
};

export const AREA_BASIS: Labels<AreaBasis> = {
  carpet: "Carpet",
  builtup: "Built-up",
  super_builtup: "Super built-up",
  plot: "Plot",
};

export const AREA_UNIT: Labels<AreaUnit> = {
  sqft: "sq ft",
  sqyd: "sq yd",
  sqm: "sq m",
};

export const ADVANTAGE_KIND: Labels<AdvantageKind> = {
  transport: "Transport",
  school: "School",
  hospital: "Hospital",
  shopping: "Shopping",
  office: "Offices",
  leisure: "Leisure",
  other: "Other",
};

export const AMENITY_CATEGORY: Labels<AmenityCategory> = {
  lifestyle: "Lifestyle",
  sports: "Sports",
  kids: "Kids",
  security: "Security",
  green: "Green",
  convenience: "Convenience",
  other: "Other",
};

export const UPDATE_STATE: Labels<UpdateState> = {
  draft: "Draft",
  published: "Published",
  archived: "Archived",
};

/** Select options from a label map, in the map's order. */
export function optionsOf<K extends string>(labels: Labels<K>): SelectOption[] {
  return (Object.entries(labels) as Array<[K, string]>).map(([value, label]) => ({
    value,
    label,
  }));
}

/** Narrows a select's string value to one of the map's keys, else returns `fallback`. */
export function keyOf<K extends string, F>(labels: Labels<K>, value: string, fallback: F): K | F {
  return Object.hasOwn(labels, value) ? (value as K) : fallback;
}
