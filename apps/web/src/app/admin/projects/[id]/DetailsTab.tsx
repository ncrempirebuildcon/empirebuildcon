"use client";
/**
 * Details tab (board NoirCmsProject, "Details"): the basics, the RERA registration and the price.
 * Saved with the editor's one "Save draft" button.
 *
 * COMPLIANCE: the RERA number is required before publishing (D-002) and price on request hides
 * prices everywhere (ARCHITECTURE §6); the warning text below comes from the approved board.
 * Money previews use the shared helpers (formatInr), never ad-hoc maths (CODE_STYLE §1).
 */
import {
  Checkbox,
  NumberField,
  Select,
  TextField,
  Textarea,
  formatInr,
  formatInrFull,
} from "@empire/ui";
import {
  AREA_UNIT,
  PROJECT_STATUS,
  PROJECT_TYPE,
  SALES_STATUS_HELP,
  keyOf,
  optionsOf,
} from "@/lib/labels";
import type { FieldErrors } from "@/lib/problems";
import { Panel } from "@/components/admin/states";
import { DEFAULT_RERA_AUTHORITY, type ProjectForm } from "./projectForm";

export interface FormTabProps {
  form: ProjectForm;
  setForm: (patch: Partial<ProjectForm>) => void;
  errors: FieldErrors;
  canWrite: boolean;
}

const SITE_HOST = "empirebuildcon.com";

/**
 * How "Off market" is limited for this user (see `offMarketLock` in ProjectEditor):
 * "none" = free choice; "no-entry" = may not choose it; "locked" = it is set and may not be left.
 */
export type OffMarketLock = "none" | "no-entry" | "locked";

const OFF_MARKET_HINTS: Record<Exclude<OffMarketLock, "none">, string> = {
  "no-entry":
    "Off market hides a live project from the website, so only someone who can publish may choose it.",
  locked:
    "This live project is off market. Only someone who can publish may change that, because it puts the project back on the website.",
};

/** "Shows as ₹ 78 L" under a rupee field, or nothing while it is empty. */
function showsAs(value: number | null, onRequest: boolean): string | undefined {
  if (value === null) return undefined;
  return onRequest ? "Shows as Price on request" : `Shows as ${formatInr(value)}`;
}

export function DetailsTab({
  form,
  setForm,
  errors,
  canWrite,
  offMarketLock = "none",
}: FormTabProps & { offMarketLock?: OffMarketLock }) {
  const salesOptions = optionsOf(SALES_STATUS_HELP).map((option) =>
    option.value === "off_market" && offMarketLock === "no-entry"
      ? { ...option, disabled: true }
      : option,
  );
  const reraOptions = [{ value: DEFAULT_RERA_AUTHORITY, label: "UP-RERA · up-rera.in" }];
  if (form.rera_authority && form.rera_authority !== DEFAULT_RERA_AUTHORITY) {
    reraOptions.push({ value: form.rera_authority, label: form.rera_authority });
  }

  return (
    <fieldset disabled={!canWrite} className="flex min-w-0 flex-col gap-5">
      <legend className="sr-only">Details</legend>
      <Panel id="basics" title="Basics">
        <div className="grid gap-x-5 gap-y-4 md:grid-cols-2">
          <TextField
            label="Project name"
            required
            maxLength={120}
            value={form.name}
            onChange={(e) => setForm({ name: e.target.value })}
            error={errors.name}
          />
          <TextField
            label="Web address (slug)"
            maxLength={120}
            value={form.slug}
            onChange={(e) => setForm({ slug: e.target.value.toLowerCase() })}
            error={errors.slug}
            hint={`${SITE_HOST}/projects/${form.slug.trim() || "[made from the name]"}`}
          />
          <TextField
            label="Tagline"
            maxLength={160}
            value={form.tagline}
            onChange={(e) => setForm({ tagline: e.target.value })}
            error={errors.tagline}
            hint="One line under the name on cards and the project page."
            className="md:col-span-2"
          />
          <Textarea
            label="Short description"
            rows={4}
            maxLength={20000}
            value={form.description}
            onChange={(e) => setForm({ description: e.target.value })}
            error={errors.description}
            placeholder="[Two or three plain sentences about the project, written by Empire's team.]"
            hint={
              <span className="flex flex-wrap justify-between gap-2">
                <span>Formatting: *bold* · _italic_ · - bullet</span>
                <span>Shown on the project page and cards</span>
              </span>
            }
            className="md:col-span-2"
          />
          <Select
            label="Construction status"
            value={form.status}
            options={optionsOf(PROJECT_STATUS)}
            onChange={(e) =>
              setForm({ status: keyOf(PROJECT_STATUS, e.target.value, form.status) })
            }
            error={errors.status}
          />
          <Select
            label="Sales status"
            value={form.sales_status}
            options={salesOptions}
            disabled={offMarketLock === "locked"}
            onChange={(e) =>
              setForm({ sales_status: keyOf(SALES_STATUS_HELP, e.target.value, form.sales_status) })
            }
            error={errors.sales_status}
            hint={offMarketLock === "none" ? undefined : OFF_MARKET_HINTS[offMarketLock]}
          />
          <Select
            label="Project type"
            value={form.project_type}
            options={optionsOf(PROJECT_TYPE)}
            onChange={(e) =>
              setForm({ project_type: keyOf(PROJECT_TYPE, e.target.value, form.project_type) })
            }
            error={errors.project_type}
          />
          <TextField
            label="Launch date"
            type="date"
            value={form.launch_date}
            onChange={(e) => setForm({ launch_date: e.target.value })}
            error={errors.launch_date}
          />
          <Checkbox
            className="md:col-span-2"
            checked={form.is_featured}
            onChange={(e) => setForm({ is_featured: e.target.checked })}
            label={
              <>
                <strong className="text-ivory">Feature on the home page</strong> — featured projects
                appear in their featured order, set below.
              </>
            }
          />
          {form.is_featured ? (
            <NumberField
              label="Featured order"
              value={form.featured_order}
              onValueChange={(featured_order) => setForm({ featured_order })}
              error={errors.featured_order}
              hint="1 shows first. Leave empty to show after the numbered ones."
              grouping={false}
            />
          ) : null}
        </div>
      </Panel>

      <Panel
        id="rera"
        title="RERA"
        description="Shown on the project page with the QR code and a link to verify on up-rera.in. The designated account is under Documents."
      >
        <div className="grid gap-x-5 gap-y-4 md:grid-cols-2">
          <Select
            label="RERA authority"
            value={form.rera_authority || DEFAULT_RERA_AUTHORITY}
            options={reraOptions}
            onChange={(e) => setForm({ rera_authority: e.target.value })}
            error={errors.rera_authority}
          />
          <TextField
            label="RERA registration number"
            maxLength={60}
            value={form.rera_number}
            placeholder="[Registration number]"
            onChange={(e) => setForm({ rera_number: e.target.value })}
            error={errors.rera_number}
            hint="Required before publishing."
          />
          <TextField
            label="RERA page link"
            type="url"
            inputMode="url"
            maxLength={500}
            value={form.rera_url}
            placeholder="https://up-rera.in/…"
            onChange={(e) => setForm({ rera_url: e.target.value })}
            error={errors.rera_url}
            hint="This project's page on the regulator's website, so buyers can check it."
          />
          <TextField
            label="Possession date (as registered with RERA)"
            type="date"
            value={form.possession_date}
            onChange={(e) => setForm({ possession_date: e.target.value })}
            error={errors.possession_date}
          />
        </div>
      </Panel>

      <PricePanel form={form} setForm={setForm} errors={errors} canWrite={canWrite} />
    </fieldset>
  );
}

function PricePanel({ form, setForm, errors }: FormTabProps) {
  const rateHint =
    form.rate_inr === null
      ? "Optional: a rate per unit of area, e.g. for plots."
      : form.price_on_request
        ? "Shows as Price on request"
        : `Shows as ${formatInrFull(form.rate_inr)} per ${AREA_UNIT[form.rate_unit || "sqft"]}`;
  return (
    <Panel
      id="price"
      title="Price"
      description="Whole rupees. Prices on the website always carry the note “excludes GST, stamp duty and registration”."
    >
      <div className="grid gap-x-5 gap-y-4 md:grid-cols-2">
        <NumberField
          label="Price from (₹)"
          prefix="₹"
          value={form.price_min_inr}
          onValueChange={(price_min_inr) => setForm({ price_min_inr })}
          error={errors["price.min_inr"]}
          hint={showsAs(form.price_min_inr, form.price_on_request)}
        />
        <NumberField
          label="Price up to (₹)"
          prefix="₹"
          value={form.price_max_inr}
          onValueChange={(price_max_inr) => setForm({ price_max_inr })}
          error={errors["price.max_inr"]}
          hint={showsAs(form.price_max_inr, form.price_on_request)}
        />
        <NumberField
          label="Rate (₹)"
          prefix="₹"
          value={form.rate_inr}
          onValueChange={(rate_inr) => setForm({ rate_inr })}
          error={errors["price.rate_inr"]}
          hint={rateHint}
        />
        <Select
          label="Rate per"
          value={form.rate_unit || "sqft"}
          options={optionsOf(AREA_UNIT)}
          onChange={(e) => setForm({ rate_unit: keyOf(AREA_UNIT, e.target.value, "sqft") })}
          error={errors["price.rate_unit"]}
        />
        <TextField
          label="Price note"
          maxLength={160}
          value={form.price_note}
          placeholder="[e.g. + GST and registration]"
          onChange={(e) => setForm({ price_note: e.target.value })}
          error={errors["price.note"]}
          className="md:col-span-2"
        />
        <Checkbox
          className="md:col-span-2"
          checked={form.price_on_request}
          onChange={(e) => setForm({ price_on_request: e.target.checked })}
          error={errors.price}
          label={
            <>
              <strong className="text-ivory">Price on request</strong> — hides prices everywhere,
              including search results and structured data. Not recommended: buyers trust projects
              that show prices.
            </>
          }
        />
      </div>
    </Panel>
  );
}
