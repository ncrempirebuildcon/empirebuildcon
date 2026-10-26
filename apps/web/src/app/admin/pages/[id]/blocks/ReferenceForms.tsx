"use client";
/**
 * Settings forms for blocks that show other CMS content: project and property cards, the enquiry
 * form, FAQs and the map (board NoirCmsPage). Numbers, testimonials and the offer banner, which
 * carry honesty rules, are in HonestyForms.tsx. The API checks every id when the page is saved
 * (content/block_refs.py).
 */
import Link from "next/link";
import { useState } from "react";
import { Checkbox, NumberField, SegmentedControl, Select, Textarea } from "@empire/ui";
import { api, call } from "@/lib/api";
import { PROJECT_STATUS, keyOf, optionsOf } from "@/lib/labels";
import { LEAD_SOURCE } from "@/lib/leads/labels";
import { FAQS_PATH } from "@/lib/routes";
import { useLoad } from "@/components/admin/useLoad";
import type { DataOf } from "./blockDraft";
import {
  HeadingField,
  IdListPicker,
  orNull,
  useCityOptions,
  useProjectOptions,
  type BlockFormProps,
} from "./fields";

type FormSource = DataOf<"lead_form">["source"];
const FORM_SOURCES: FormSource[] = [
  "contact_form",
  "project_form",
  "campaign",
  "site_visit",
  "brochure",
];

export function GridForm({
  data,
  onChange,
  errors,
  idPrefix,
  kind,
}: BlockFormProps<DataOf<"project_grid">> & { kind: "project_grid" | "property_grid" }) {
  const cities = useCityOptions();
  return (
    <>
      <HeadingField data={data} onChange={onChange} errors={errors} idPrefix={idPrefix} />
      <Select
        id={`${idPrefix}-status`}
        label="Construction status"
        value={data.status ?? ""}
        placeholder="Any status"
        options={optionsOf(PROJECT_STATUS)}
        onChange={(event) =>
          onChange({ ...data, status: keyOf(PROJECT_STATUS, event.target.value, null) })
        }
        error={errors.status}
      />
      <Select
        id={`${idPrefix}-city`}
        label="City"
        value={data.city_id ?? ""}
        placeholder="Any city"
        options={cities}
        onChange={(event) => onChange({ ...data, city_id: event.target.value || null })}
        error={errors.city_id}
      />
      <Checkbox
        checked={data.featured_only}
        onChange={(event) => onChange({ ...data, featured_only: event.target.checked })}
        label="Featured projects only, in the order set on the Projects list"
      />
      <NumberField
        id={`${idPrefix}-limit`}
        label="Cards to show (1–24)"
        value={data.limit}
        onValueChange={(limit) => onChange({ ...data, limit: limit ?? 6 })}
        error={errors.limit}
      />
      <Checkbox
        checked={data.show_status_tabs}
        onChange={(event) => onChange({ ...data, show_status_tabs: event.target.checked })}
        label="Show status tabs (All · Ongoing · Completed)"
      />
      <p className="text-caption text-muted">
        {kind === "project_grid" ? "Sold-out projects" : "Sold-out properties"} always appear after
        available ones. Off-market and sample items never appear on the live site.
      </p>
    </>
  );
}

export function LeadFormForm({
  data,
  onChange,
  errors,
  idPrefix,
}: BlockFormProps<DataOf<"lead_form">>) {
  const projects = useProjectOptions();
  return (
    <>
      <HeadingField data={data} onChange={onChange} errors={errors} idPrefix={idPrefix} />
      <Textarea
        id={`${idPrefix}-intro`}
        label="Intro text (optional)"
        rows={2}
        maxLength={500}
        value={data.intro ?? ""}
        onChange={(event) => onChange({ ...data, intro: orNull(event.target.value) })}
        error={errors.intro}
      />
      <Select
        id={`${idPrefix}-source`}
        label="Which form"
        value={data.source}
        options={FORM_SOURCES.map((source) => ({ value: source, label: LEAD_SOURCE[source] }))}
        onChange={(event) =>
          onChange({
            ...data,
            source: FORM_SOURCES.find((s) => s === event.target.value) ?? "contact_form",
          })
        }
        error={errors.source}
        hint="Enquiries are recorded with this source in the leads inbox."
      />
      <Select
        id={`${idPrefix}-project`}
        label="Project (optional)"
        value={data.project_id ?? ""}
        placeholder={projects.loading ? "Loading projects…" : "General enquiry (no project)"}
        options={projects.options}
        onChange={(event) => onChange({ ...data, project_id: event.target.value || null })}
        error={errors.project_id}
      />
      <p className="text-caption text-muted">
        The form shows the current consent text with separate, unticked required and optional boxes.
        Visitors can send it once the public site is live (Phase 5).
      </p>
    </>
  );
}

export function FaqListForm({
  data,
  onChange,
  errors,
  idPrefix,
}: BlockFormProps<DataOf<"faq_list">>) {
  const projects = useProjectOptions();
  const faqs = useLoad("block-faqs", () =>
    call(api.GET("/api/v1/admin/faqs", { params: { query: { per_page: 100 } } })),
  );
  // WHY local state: "Pick" with nothing picked yet saves the same data as "Site-wide".
  const [current, setMode] = useState<"site" | "project" | "pick">(() =>
    (data.faq_ids ?? []).length > 0 ? "pick" : data.project_id ? "project" : "site",
  );
  const setCurrent = (next: "site" | "project" | "pick") => {
    setMode(next);
    if (next === "site") onChange({ ...data, project_id: null, faq_ids: [] });
    if (next === "project") onChange({ ...data, project_id: data.project_id, faq_ids: [] });
    if (next === "pick") onChange({ ...data, project_id: null });
  };
  return (
    <>
      <HeadingField data={data} onChange={onChange} errors={errors} idPrefix={idPrefix} />
      <SegmentedControl
        label="Which FAQs"
        value={current}
        options={[
          { value: "site", label: "Site-wide" },
          { value: "project", label: "A project's" },
          { value: "pick", label: "Pick" },
        ]}
        onChange={setCurrent}
      />
      {errors[""] ? <p className="text-caption text-danger">{errors[""]}</p> : null}
      {current === "project" ? (
        <Select
          id={`${idPrefix}-project`}
          label="Project"
          value={data.project_id ?? ""}
          placeholder={projects.loading ? "Loading projects…" : "Choose a project"}
          options={projects.options}
          onChange={(event) => onChange({ ...data, project_id: event.target.value || null })}
          error={errors.project_id}
          hint={data.project_id ? undefined : "Until a project is chosen, the site-wide FAQs show."}
        />
      ) : null}
      {current === "pick" ? (
        <IdListPicker
          idPrefix={`${idPrefix}-faqs`}
          label="Chosen FAQs"
          max={24}
          value={data.faq_ids ?? []}
          onChange={(faq_ids) => onChange({ ...data, faq_ids })}
          options={(faqs.data?.items ?? []).map((faq) => ({
            value: faq.id,
            label: faq.question,
          }))}
          error={errors.faq_ids}
          emptyText="No FAQs chosen yet."
        />
      ) : null}
      <p className="text-caption text-muted">
        Only FAQs set to show on the website appear.{" "}
        <Link href={FAQS_PATH} className="underline">
          Edit FAQs
        </Link>
      </p>
    </>
  );
}

export function MapForm({ data, onChange, errors, idPrefix }: BlockFormProps<DataOf<"map">>) {
  const projects = useProjectOptions();
  return (
    <>
      <HeadingField data={data} onChange={onChange} errors={errors} idPrefix={idPrefix} />
      <Select
        id={`${idPrefix}-project`}
        label="Project"
        required
        value={data.project_id}
        placeholder={projects.loading ? "Loading projects…" : "Choose a project"}
        options={projects.options}
        onChange={(event) => onChange({ ...data, project_id: event.target.value })}
        error={errors.project_id}
        hint="The pin comes from the project's Location tab."
      />
    </>
  );
}
