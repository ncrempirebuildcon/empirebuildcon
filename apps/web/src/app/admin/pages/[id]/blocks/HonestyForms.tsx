"use client";
/**
 * Settings forms for the blocks with honesty rules (board NoirCmsPage; AGENTS.md "Honest
 * content"):
 *   - Numbers: each needs where it comes from and the date it was true (COMPLIANCE).
 *   - Testimonials: only real, consented ones can ever show; the block stays hidden otherwise.
 *   - Offer banner: shows the end date as plain text with the terms; no countdowns exist. Only
 *     `offers.manage` can pick one offer (see OfferBannerForm).
 * The API checks the same rules and every id (content/blocks.py, block_refs.py).
 */
import Link from "next/link";
import { useState } from "react";
import { NumberField, SegmentedControl, Select, TextField } from "@empire/ui";
import { api, call } from "@/lib/api";
import { OFFER_PLACEMENT, OFFER_STATE } from "@/lib/content/labels";
import { keyOf, optionsOf } from "@/lib/labels";
import { OFFERS_PATH, TESTIMONIALS_PATH } from "@/lib/routes";
import { ErrorPanel } from "@/components/admin/states";
import { useLoad } from "@/components/admin/useLoad";
import { useAdminSession } from "../../../session-context";
import { emptyStat, type DataOf } from "./blockDraft";
import {
  HeadingField,
  IdListPicker,
  ItemsEditor,
  OptionalText,
  useProjectOptions,
  type BlockFormProps,
} from "./fields";

export function StatsForm({ data, onChange, errors, idPrefix }: BlockFormProps<DataOf<"stats">>) {
  return (
    <>
      <p className="rounded-tile border border-gold-line-strong bg-gold-tint px-3.5 py-2.5 text-caption text-gold-300">
        Numbers must be real. Each one needs where it comes from (e.g. completion certificates,
        handover records) and the date it was true. Leave the block hidden until they are checked.
      </p>
      <HeadingField data={data} onChange={onChange} errors={errors} idPrefix={idPrefix} />
      <ItemsEditor
        items={data.items}
        onChange={(items) => onChange({ ...data, items })}
        noun="Number"
        min={1}
        max={6}
        make={emptyStat}
        addLabel="+ Add a number"
        render={(item, index, set) => (
          <>
            <div className="flex flex-wrap gap-3">
              <TextField
                id={`${idPrefix}-items-${index}-value`}
                label="Number"
                required
                maxLength={20}
                value={item.value}
                placeholder="[n]"
                onChange={(event) => set({ value: event.target.value })}
                error={errors[`items.${index}.value`]}
                className="min-w-0 flex-[1_1_100px]"
              />
              <TextField
                id={`${idPrefix}-items-${index}-label`}
                label="What it counts"
                required
                maxLength={60}
                value={item.label}
                placeholder="[homes handed over]"
                onChange={(event) => set({ label: event.target.value })}
                error={errors[`items.${index}.label`]}
                className="min-w-0 flex-[2_1_180px]"
              />
            </div>
            <TextField
              id={`${idPrefix}-items-${index}-source`}
              label="Where this number comes from"
              required
              maxLength={160}
              value={item.source}
              placeholder="[e.g. possession letters register]"
              onChange={(event) => set({ source: event.target.value })}
              error={errors[`items.${index}.source`]}
            />
            <TextField
              id={`${idPrefix}-items-${index}-as-of`}
              label="True as of"
              required
              type="date"
              value={item.as_of}
              onChange={(event) => set({ as_of: event.target.value })}
              error={errors[`items.${index}.as_of`]}
              className="max-w-60"
            />
          </>
        )}
      />
      <OptionalText
        id={`${idPrefix}-note`}
        label="Note under the numbers"
        maxLength={250}
        value={data.note}
        onChange={(note) => onChange({ ...data, note })}
        error={errors.note}
      />
    </>
  );
}

export function TestimonialsForm({
  data,
  onChange,
  errors,
  idPrefix,
}: BlockFormProps<DataOf<"testimonials">>) {
  const projects = useProjectOptions();
  const testimonials = useLoad("block-testimonials", () =>
    call(api.GET("/api/v1/admin/testimonials", { params: { query: { per_page: 100 } } })),
  );
  // WHY local state: "Pick" with nothing picked yet saves the same data as "Newest".
  const [mode, setMode] = useState<"newest" | "project" | "pick">(() =>
    (data.testimonial_ids ?? []).length > 0 ? "pick" : data.project_id ? "project" : "newest",
  );
  return (
    <>
      <p className="rounded-tile border border-gold-line-strong bg-gold-tint px-3.5 py-2.5 text-caption text-gold-300">
        Real testimonials only. The website shows this block only when testimonials with a recorded
        source and the buyer&apos;s permission exist; otherwise it stays hidden.
      </p>
      <HeadingField data={data} onChange={onChange} errors={errors} idPrefix={idPrefix} />
      <SegmentedControl
        label="Which testimonials"
        value={mode}
        options={[
          { value: "newest", label: "Newest" },
          { value: "project", label: "A project's" },
          { value: "pick", label: "Pick" },
        ]}
        onChange={(next) => {
          setMode(next);
          if (next === "newest") onChange({ ...data, project_id: null, testimonial_ids: [] });
          if (next === "project") onChange({ ...data, testimonial_ids: [] });
          if (next === "pick") onChange({ ...data, project_id: null });
        }}
      />
      {errors[""] ? <p className="text-caption text-danger">{errors[""]}</p> : null}
      {mode === "project" ? (
        <Select
          id={`${idPrefix}-project`}
          label="Project"
          value={data.project_id ?? ""}
          placeholder="Choose a project"
          options={projects.options}
          onChange={(event) => onChange({ ...data, project_id: event.target.value || null })}
          error={errors.project_id}
          hint={
            data.project_id ? undefined : "Until a project is chosen, the newest testimonials show."
          }
        />
      ) : null}
      {mode === "pick" ? (
        <IdListPicker
          idPrefix={`${idPrefix}-testimonials`}
          label="Chosen testimonials"
          max={24}
          value={data.testimonial_ids ?? []}
          onChange={(testimonial_ids) => onChange({ ...data, testimonial_ids })}
          options={(testimonials.data?.items ?? []).map((t) => ({
            value: t.id,
            label: `${t.person_name}${t.is_visible ? "" : " (not shown on the website)"}`,
          }))}
          error={errors.testimonial_ids}
          emptyText="None chosen. Add real testimonials first under Offers & blog → Testimonials."
        />
      ) : (
        <NumberField
          id={`${idPrefix}-limit`}
          label="How many to show (1–12)"
          value={data.limit}
          onValueChange={(limit) => onChange({ ...data, limit: limit ?? 3 })}
          error={errors.limit}
        />
      )}
      <p className="text-caption text-muted">
        <Link href={TESTIMONIALS_PATH} className="underline">
          Manage testimonials
        </Link>
      </p>
    </>
  );
}

/**
 * Which offer a banner block shows: the live offer for a placement, or one chosen offer.
 *
 * WHY by permission (review L3): the offer list (`GET /admin/offers`) needs `offers.manage`,
 * which content editors don't have (ARCHITECTURE.md §11). Without it, the block offers the
 * placement only; an offer someone else picked stays, shown read-only, and there is no link to
 * the Offers screen they can't open.
 */
export function OfferBannerForm({
  data,
  onChange,
  errors,
  idPrefix,
}: BlockFormProps<DataOf<"offer_banner">>) {
  const canPickOffer = useAdminSession().can("offers.manage");
  const offers = useLoad(`block-offers:${canPickOffer}`, () =>
    canPickOffer
      ? call(api.GET("/api/v1/admin/offers", { params: { query: { per_page: 100 } } }))
      : Promise.resolve(null),
  );
  // WHY local state: "One offer" with nothing chosen yet has neither an offer nor a placement.
  const [mode, setMode] = useState<"placement" | "offer">(() =>
    data.offer_id ? "offer" : "placement",
  );
  const noCountdowns = (
    <>
      The banner shows the offer&apos;s end date as plain text with its terms; there are no
      countdown timers.
    </>
  );
  if (!canPickOffer && data.offer_id) {
    return (
      <>
        <div
          role="group"
          aria-labelledby={`${idPrefix}-offer-label`}
          className="rounded-tile border border-line bg-noir-900 px-3.5 py-2.5"
        >
          <p id={`${idPrefix}-offer-label`} className="text-small font-semibold text-ivory">
            Offer chosen by an offers manager
          </p>
          <p className="mt-0.5 text-caption text-muted">
            Only someone who manages offers can change which offer this block shows.
          </p>
        </div>
        <p className="text-caption text-muted">{noCountdowns}</p>
      </>
    );
  }
  return (
    <>
      {canPickOffer ? (
        <SegmentedControl
          label="Which offer"
          value={mode}
          options={[
            { value: "placement", label: "Live offer for a placement" },
            { value: "offer", label: "One offer" },
          ]}
          onChange={(next) => {
            setMode(next);
            onChange(
              next === "offer"
                ? { offer_id: offers.data?.items[0]?.id ?? null, placement: null }
                : { offer_id: null, placement: "banner" },
            );
          }}
        />
      ) : null}
      {errors[""] ? <p className="text-caption text-danger">{errors[""]}</p> : null}
      {mode === "offer" && canPickOffer ? (
        offers.error ? (
          <ErrorPanel message="Couldn't load the offers." onRetry={offers.reload} />
        ) : (
          <Select
            id={`${idPrefix}-offer`}
            label="Offer"
            value={data.offer_id ?? ""}
            placeholder={offers.loading ? "Loading offers…" : "Choose an offer"}
            options={(offers.data?.items ?? []).map((offer) => ({
              value: offer.id,
              label: `${offer.title} · ${OFFER_STATE[offer.state]}`,
            }))}
            onChange={(event) => onChange({ ...data, offer_id: event.target.value || null })}
            error={errors.offer_id}
          />
        )
      ) : (
        <Select
          id={`${idPrefix}-placement`}
          label="Placement"
          value={data.placement ?? "banner"}
          options={optionsOf(OFFER_PLACEMENT)}
          onChange={(event) =>
            onChange({ ...data, placement: keyOf(OFFER_PLACEMENT, event.target.value, "banner") })
          }
          error={errors.placement}
          hint="Shows the highest-priority offer that is live for this placement, or nothing."
        />
      )}
      <p className="text-caption text-muted">
        {noCountdowns}
        {canPickOffer ? (
          <>
            {" "}
            <Link href={OFFERS_PATH} className="underline">
              Manage offers
            </Link>
          </>
        ) : null}
      </p>
    </>
  );
}
