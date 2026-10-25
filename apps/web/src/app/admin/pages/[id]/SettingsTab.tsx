"use client";
/**
 * The page editor's Settings tab: title, web address with its preview, kind, legal version,
 * menu place and the publishing schedule (spec Phase 4 part 4 §2). Saved with "Save draft".
 *
 * Pages that come with the website (`is_required`: the system pages home, about, contact and
 * projects, and the seeded legal pages privacy, terms and disclaimer) keep their kind and
 * address: other parts of the site, the consent texts and the footer link to them (review L8;
 * the API refuses the change too).
 */
import { Checkbox, NumberField, Select, TextField } from "@empire/ui";
import { istToday } from "@empire/ui/format";
import { PAGE_KIND, PAGE_KIND_HELP, type PageKind } from "@/lib/content/labels";
import { keyOf } from "@/lib/labels";
import type { FieldErrors } from "@/lib/problems";
import { IstDateTimeField } from "@/components/admin/content/IstDateTimeField";
import { Panel } from "@/components/admin/states";
import type { FormProblems, Page, PageForm } from "./pageForm";

const CHOOSABLE: PageKind[] = ["standard", "landing", "legal"];

export interface SettingsTabProps {
  page: Page;
  form: PageForm;
  setForm: (patch: Partial<PageForm>) => void;
  /** API errors and form checks, keyed by field ("slug", "nav_order"). */
  errors: FieldErrors;
  schedule: Pick<FormProblems, "publish_at" | "unpublish_at">;
  canWrite: boolean;
  /** Setting the schedule is a publishing decision (content.publish, or legal.publish). */
  canPublish: boolean;
  /** Making a page legal, or a legal page something else, needs legal.publish. */
  canChooseLegal: boolean;
}

export function SettingsTab({
  page,
  form,
  setForm,
  errors,
  schedule,
  canWrite,
  canPublish,
  canChooseLegal,
}: SettingsTabProps) {
  const isFixed = page.is_required;
  const isLive = page.publish_state === "published";
  const isHome = page.kind === "system" && page.slug === "home";
  const address = isHome ? "/" : `/${form.slug || "[web-address]"}`;
  return (
    <fieldset disabled={!canWrite} className="flex min-w-0 flex-col gap-5">
      <legend className="sr-only">Page settings</legend>
      <Panel id="page-basics" title="Page">
        <TextField
          id="page-title"
          label="Title"
          required
          maxLength={120}
          value={form.title}
          onChange={(event) => setForm({ title: event.target.value })}
          error={errors.title}
        />
        <TextField
          id="page-slug"
          label="Web address"
          required
          maxLength={120}
          disabled={isFixed}
          value={form.slug}
          onChange={(event) => setForm({ slug: event.target.value.trim().toLowerCase() })}
          error={errors.slug}
          hint={
            <span className="flex flex-col gap-0.5">
              <span>
                Shown as <strong className="text-ivory">empirebuildcon.com{address}</strong>
              </span>
              {isFixed ? (
                <span>This page comes with the website: it keeps its web address.</span>
              ) : page.publish_state === "published" ? (
                <span>
                  This page is live: changing the address makes the old one redirect here (308),
                  listed under Redirects.
                </span>
              ) : (
                <span>Lower-case letters, numbers and hyphens.</span>
              )}
            </span>
          }
        />
        {isFixed ? (
          <p className="text-small">
            Kind: <strong className="text-ivory">{PAGE_KIND[page.kind]}</strong>.{" "}
            <span className="text-muted">
              {page.kind === "system"
                ? PAGE_KIND_HELP.system
                : "This page comes with the website: it keeps its kind and can't be deleted."}
            </span>
          </p>
        ) : (
          <Select
            id="page-kind"
            label="Kind"
            value={form.kind}
            // SECURITY (mirrors the API): only legal.publish moves a page into or out of "legal".
            disabled={page.kind === "legal" && !canChooseLegal}
            options={CHOOSABLE.filter(
              (value) => value !== "legal" || canChooseLegal || page.kind === "legal",
            ).map((value) => ({ value, label: PAGE_KIND[value] }))}
            onChange={(event) => setForm({ kind: keyOf(PAGE_KIND, event.target.value, form.kind) })}
            error={errors.kind}
            hint={PAGE_KIND_HELP[form.kind]}
          />
        )}
        {form.kind === "legal" ? (
          <TextField
            id="page-legal-version"
            label="Legal text version (optional)"
            maxLength={20}
            value={form.legal_version}
            placeholder="[1.0]"
            onChange={(event) => setForm({ legal_version: event.target.value })}
            error={errors.legal_version}
            hint="Raise it whenever the approved wording changes, so records can say which version applied."
          />
        ) : null}
      </Panel>

      <Panel id="page-menu" title="Website menu">
        <Checkbox
          checked={form.show_in_nav}
          onChange={(event) => setForm({ show_in_nav: event.target.checked })}
          label="Show this page in the website menu"
        />
        {form.show_in_nav ? (
          <NumberField
            id="page-nav-order"
            label="Position in the menu"
            value={form.nav_order}
            onValueChange={(nav_order) => setForm({ nav_order })}
            error={errors.nav_order}
            hint="Lower numbers come first. Pages that aren't published never appear in the menu."
            className="max-w-60"
          />
        ) : null}
      </Panel>

      <Panel
        id="page-schedule"
        title="Schedule"
        description="Optional. Times are India time. The schedule is checked every 15 minutes, so a change can happen up to 15 minutes after the time set."
      >
        {!canPublish ? (
          <p className="text-caption text-muted">
            Scheduling is a publishing decision: it needs the{" "}
            {page.kind === "legal" ? "legal.publish" : "content.publish"} permission.
          </p>
        ) : null}
        <IstDateTimeField
          id="page-publish-at"
          legend="Publish on"
          value={form.publish_at}
          onChange={(publish_at) => setForm({ publish_at })}
          error={
            schedule.publish_at ??
            (errors.publish_at ? { field: "date", message: errors.publish_at } : null)
          }
          min={istToday()}
          // WHY disabled while live (review M2): a publish date on a live page does nothing until
          // the page is taken down, and then it would bring the page back unasked.
          disabled={!canPublish || isLive}
          hint={
            isLive
              ? "The page is live already. To publish it again on a date, unpublish it first."
              : "Leave empty to publish by hand."
          }
        />
        <IstDateTimeField
          id="page-unpublish-at"
          legend="Take down on"
          value={form.unpublish_at}
          onChange={(unpublish_at) => setForm({ unpublish_at })}
          error={
            schedule.unpublish_at ??
            (errors.unpublish_at ? { field: "date", message: errors.unpublish_at } : null)
          }
          min={istToday()}
          disabled={!canPublish}
          hint="Leave empty to keep it live until someone unpublishes it."
        />
      </Panel>
    </fieldset>
  );
}
