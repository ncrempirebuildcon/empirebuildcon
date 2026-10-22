"use client";
/**
 * The add/edit form fields for one configuration (board NoirCmsProject, "Configurations").
 *
 * COMPLIANCE: carpet area is typed in sq ft, and the sq m figure under it is worked out "auto"
 * with the shared helper (sqftToSqm), so the two never disagree. Money previews use formatInr.
 */
import { Checkbox, NumberField, Select, TextField, formatInr, sqftToSqm } from "@empire/ui";
import type { Schema } from "@/lib/api";
import {
  AREA_BASIS,
  AREA_UNIT,
  PROPERTY_TYPE,
  SALES_STATUS_HELP,
  keyOf,
  optionsOf,
} from "@/lib/labels";
import { MediaPlaceholder } from "@/components/admin/states";
import type { Collection } from "@/components/admin/useCollection";
import type { ConfigurationDraft } from "./configurationDraft";
import type { Configuration } from "./editorTypes";

export function ConfigurationFields({
  collection: c,
  towers,
}: {
  collection: Collection<Configuration, ConfigurationDraft>;
  towers: readonly Schema<"Tower">[];
}) {
  const d = c.draft;
  if (!d) return null;
  const set = c.setDraft;
  const errors = c.errors;
  const basis = AREA_BASIS[d.basis];
  const autoSqm = (sqft: number | null) =>
    sqft === null ? undefined : `${sqftToSqm(sqft).toFixed(1)} sq m · auto`;
  const shows = (value: number | null) =>
    value === null
      ? undefined
      : d.price_on_request
        ? "Shows as Price on request"
        : `Shows as ${formatInr(value)}`;

  return (
    <div className="grid gap-x-5 gap-y-4 md:grid-cols-2">
      <TextField
        label="Name"
        required
        maxLength={80}
        value={d.name}
        placeholder="[e.g. 2 BHK Classic]"
        onChange={(e) => set({ name: e.target.value })}
        error={errors.name}
      />
      <TextField
        label="Web address (slug)"
        maxLength={120}
        value={d.slug}
        onChange={(e) => set({ slug: e.target.value.toLowerCase() })}
        error={errors.slug}
        hint="Made from the name if left empty."
      />
      <Select
        label="Tower"
        value={d.tower_id}
        placeholder="All towers"
        options={towers.map((t) => ({ value: t.id, label: t.name }))}
        onChange={(e) => set({ tower_id: e.target.value })}
        error={errors.tower_id}
      />
      <Select
        label="Property type"
        value={d.property_type}
        options={optionsOf(PROPERTY_TYPE)}
        onChange={(e) =>
          set({ property_type: keyOf(PROPERTY_TYPE, e.target.value, d.property_type) })
        }
        error={errors.property_type}
      />
      <NumberField
        label="BHK"
        decimals={1}
        value={d.bhk}
        onValueChange={(bhk) => set({ bhk })}
        error={errors.bhk}
        hint="e.g. 2 or 2.5"
      />
      <div className="grid grid-cols-2 gap-4">
        <NumberField
          label="Bathrooms"
          value={d.bathrooms}
          onValueChange={(bathrooms) => set({ bathrooms })}
          error={errors.bathrooms}
        />
        <NumberField
          label="Balconies"
          value={d.balconies}
          onValueChange={(balconies) => set({ balconies })}
          error={errors.balconies}
        />
      </div>
      <Select
        label="Area basis"
        value={d.basis}
        options={optionsOf(AREA_BASIS)}
        onChange={(e) => set({ basis: keyOf(AREA_BASIS, e.target.value, d.basis) })}
        error={errors["area.basis"]}
        hint="RERA pages show carpet area; use another basis only for plots or shops."
      />
      <Select
        label="Show area on the website in"
        value={d.display_unit}
        options={optionsOf(AREA_UNIT)}
        onChange={(e) => set({ display_unit: keyOf(AREA_UNIT, e.target.value, d.display_unit) })}
        error={errors["area.display_unit"]}
      />
      <NumberField
        label={`${basis} area from (sq ft)`}
        suffix="sq ft"
        value={d.area_min_sqft}
        onValueChange={(area_min_sqft) => set({ area_min_sqft })}
        error={errors["area.min_sqm"] ?? errors.area}
        hint={autoSqm(d.area_min_sqft)}
      />
      <NumberField
        label={`${basis} area up to (sq ft, optional)`}
        suffix="sq ft"
        value={d.area_max_sqft}
        onValueChange={(area_max_sqft) => set({ area_max_sqft })}
        error={errors["area.max_sqm"]}
        hint={autoSqm(d.area_max_sqft)}
      />
      <NumberField
        label="Price from (₹)"
        prefix="₹"
        value={d.price_min_inr}
        onValueChange={(price_min_inr) => set({ price_min_inr })}
        error={errors["price.min_inr"] ?? errors.price}
        hint={shows(d.price_min_inr)}
      />
      <NumberField
        label="Price up to (₹, optional)"
        prefix="₹"
        value={d.price_max_inr}
        onValueChange={(price_max_inr) => set({ price_max_inr })}
        error={errors["price.max_inr"]}
        hint={shows(d.price_max_inr)}
      />
      <Select
        label="Availability"
        value={d.sales_status}
        options={optionsOf(SALES_STATUS_HELP)}
        onChange={(e) =>
          set({ sales_status: keyOf(SALES_STATUS_HELP, e.target.value, d.sales_status) })
        }
        error={errors.sales_status}
      />
      <Checkbox
        className="self-end"
        checked={d.price_on_request}
        onChange={(e) => set({ price_on_request: e.target.checked })}
        label={
          <>
            <strong className="text-ivory">Price on request</strong> for this configuration
          </>
        }
      />
      <div className="md:col-span-2">
        <MediaPlaceholder what="Floor plans for this configuration are added in the media manager." />
      </div>
    </div>
  );
}
