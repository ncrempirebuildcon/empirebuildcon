"use client";
/**
 * The offer editor beside the list (board NoirCmsContent, "Edit offer"): name, project,
 * placement, details, image, button, terms, dates in India time, priority and on/off.
 *
 * How it works:
 *   1. "Save offer" creates (POST) or saves the changed fields (PATCH, offerForm.ts) after the
 *      checks in offerForm.ts; API field errors appear next to their fields.
 *   2. The state chip comes from the API (`state`: scheduled, live, ended, inactive); the line
 *      under it says what that means and when the offer ends on its own.
 *   3. Delete is offered only for an offer that was never live (`has_been_live`); others stay for
 *      the record. It asks first.
 * COMPLIANCE (AGENTS.md "No fake urgency"): the guidance line is always shown; no field for a
 * countdown exists.
 */
import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Checkbox,
  Chip,
  ConfirmDialog,
  NumberField,
  Select,
  TextField,
  Textarea,
} from "@empire/ui";
import { api, call } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import {
  OFFER_PLACEMENT,
  OFFER_STATE,
  OFFER_STATE_CHIP,
  OFFER_STATE_HELP,
} from "@/lib/content/labels";
import { keyOf, optionsOf } from "@/lib/labels";
import { fieldErrors, problemMessage, type FieldErrors } from "@/lib/problems";
import { IstDateTimeField } from "@/components/admin/content/IstDateTimeField";
import { MediaField } from "@/components/admin/media/MediaField";
import { useLoad } from "@/components/admin/useLoad";
import { useAdminSession } from "../session-context";
import {
  EMPTY_OFFER,
  checkForm,
  hasProblems,
  sameForm,
  toCreate,
  toForm,
  toUpdate,
  type Offer,
  type OfferForm,
} from "./offerForm";

export interface OfferEditorProps {
  /** The offer to edit, or null for a new one. */
  offer: Offer | null;
  onDirtyChange: (dirty: boolean) => void;
  /** After a save or delete: the saved offer (null after delete) and a sentence to show. */
  onSaved: (offer: Offer | null, message: string) => Promise<void>;
  onClose: () => void;
}

export function OfferEditor({ offer, onDirtyChange, onSaved, onClose }: OfferEditorProps) {
  const { can } = useAdminSession();
  const canUpload = can("media.upload");
  const [form, setFormState] = useState<OfferForm>(() => (offer ? toForm(offer) : EMPTY_OFFER));
  const saved = offer ? toForm(offer) : EMPTY_OFFER;
  const [apiErrors, setApiErrors] = useState<FieldErrors>({});
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const projects = useLoad("offer-projects", () =>
    call(api.GET("/api/v1/admin/projects", { params: { query: { per_page: 100 } } })),
  );

  const dirty = offer === null ? !sameForm(form, EMPTY_OFFER) : !sameForm(form, saved);
  useEffect(() => {
    onDirtyChange(dirty || uploading);
  }, [dirty, uploading, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);

  const problems = checkForm(form);
  const errors: FieldErrors = { ...apiErrors, ...(checked ? problems.fields : {}) };
  const set = (patch: Partial<OfferForm>) => setFormState((current) => ({ ...current, ...patch }));

  async function save() {
    if (busy) return;
    setError(null);
    if (hasProblems(problems)) {
      setChecked(true);
      setError("Some fields need attention.");
      return;
    }
    setBusy(true);
    try {
      const result = offer
        ? await call(
            api.PATCH("/api/v1/admin/offers/{id}", {
              params: { path: { id: offer.id } },
              body: toUpdate(form, saved),
            }),
          )
        : await call(api.POST("/api/v1/admin/offers", { body: toCreate(form) }));
      setApiErrors({});
      onDirtyChange(false);
      await onSaved(
        result,
        `${offer ? "Saved" : "Added"} “${result.title}”: ${OFFER_STATE[result.state].toLowerCase()}. ${OFFER_STATE_HELP[result.state]}`,
      );
    } catch (err) {
      setApiErrors(fieldErrors(err));
      setError(problemMessage(err, "Couldn't save the offer."));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!offer) return;
    setBusy(true);
    setDeleteError(null);
    try {
      await call(api.DELETE("/api/v1/admin/offers/{id}", { params: { path: { id: offer.id } } }));
      onDirtyChange(false);
      setDeleting(false);
      await onSaved(null, `“${offer.title}” was deleted.`);
    } catch (err) {
      setDeleteError(problemMessage(err, "Couldn't delete the offer."));
    } finally {
      setBusy(false);
    }
  }

  const projectOptions = (projects.data?.items ?? []).map((project) => ({
    value: project.id,
    label: project.is_sample ? `${project.name} (SAMPLE)` : project.name,
  }));
  const title = offer ? "Edit offer" : "New offer";

  return (
    <section
      aria-labelledby="offer-editor-title"
      className="flex min-w-0 flex-[1_1_340px] flex-col gap-4 rounded-card border border-gold-line-strong bg-noir-800 p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="offer-editor-title" className="text-[17px] font-bold">
          {title}
        </h2>
        {offer ? (
          <span className="flex items-center gap-2">
            {offer.is_sample ? <Chip variant="sample">SAMPLE</Chip> : null}
            <Chip variant={OFFER_STATE_CHIP[offer.state]}>{OFFER_STATE[offer.state]}</Chip>
          </span>
        ) : null}
      </div>
      {offer ? (
        <p className="text-caption text-muted">
          {OFFER_STATE_HELP[offer.state]}
          {offer.ends_at && offer.state !== "ended"
            ? ` Ends on its own on ${formatDateTime(offer.ends_at)}; the site then hides it.`
            : ""}
        </p>
      ) : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      <form
        noValidate
        aria-label={title}
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
        className="flex flex-col gap-4"
      >
        <fieldset disabled={busy} className="flex min-w-0 flex-col gap-4">
          <legend className="sr-only">{title}</legend>
          <TextField
            id="offer-title"
            label="Offer name"
            required
            maxLength={120}
            value={form.title}
            onChange={(event) => set({ title: event.target.value })}
            error={errors.title}
          />
          <Select
            id="offer-placement"
            label="Shown on"
            value={form.placement}
            options={optionsOf(OFFER_PLACEMENT)}
            onChange={(event) =>
              set({ placement: keyOf(OFFER_PLACEMENT, event.target.value, "banner") })
            }
            error={errors.placement}
          />
          <Select
            id="offer-project"
            label={form.placement === "project" ? "Project" : "Project (optional)"}
            required={form.placement === "project"}
            value={form.project_id}
            placeholder={projects.loading ? "Loading projects…" : "All projects"}
            options={projectOptions}
            onChange={(event) => set({ project_id: event.target.value })}
            error={errors.project_id}
          />
          <Textarea
            id="offer-body"
            label="Details shown to buyers (optional)"
            rows={3}
            maxLength={500}
            value={form.body}
            placeholder="[Offer details exactly as approved by Empire, with any conditions]"
            onChange={(event) => set({ body: event.target.value })}
            error={errors.body}
          />
          <div
            role="note"
            className="rounded-tile border border-gold-line-strong bg-gold-tint px-3.5 py-2.5 text-caption text-gold-300"
          >
            <strong>No countdown timers or &ldquo;only N left&rdquo; wording.</strong> Say what the
            offer includes and until when it is valid. The site shows the end date as plain text,
            next to the terms. Keep the text factual: no promised returns or price rises.
          </div>
          <TextField
            id="offer-terms"
            label="Terms line (optional)"
            maxLength={250}
            value={form.terms}
            placeholder="[What it includes, who qualifies, until when]"
            onChange={(event) => set({ terms: event.target.value })}
            error={errors.terms}
            hint="Needed, or a terms link, when the offer mentions a price or a discount."
          />
          <TextField
            id="offer-terms-url"
            label="Terms & conditions link (optional)"
            maxLength={500}
            value={form.terms_url}
            placeholder="/offers/[offer]/terms"
            onChange={(event) => set({ terms_url: event.target.value.trim() })}
            error={errors.terms_url}
            hint="A page on this site or a full https:// address."
          />
          <MediaField
            id="offer-image"
            label="Image (optional)"
            kind="image"
            labelRequired
            value={form.image}
            onChange={(image) => set({ image })}
            canUpload={canUpload}
            error={errors.image_media_id}
            hint="Shown with its honest label (artist's impression or actual photo)."
            onBusyChange={setUploading}
          />
          <div className="flex flex-wrap gap-3">
            <TextField
              id="offer-cta-label"
              label="Button text (optional)"
              maxLength={40}
              value={form.cta_label}
              onChange={(event) => set({ cta_label: event.target.value })}
              error={errors.cta_label}
              className="min-w-0 flex-[1_1_150px]"
            />
            <TextField
              id="offer-cta-url"
              label="Button link"
              maxLength={500}
              value={form.cta_url}
              placeholder="/contact"
              onChange={(event) => set({ cta_url: event.target.value.trim() })}
              error={errors.cta_url}
              className="min-w-0 flex-[2_1_180px]"
            />
          </div>
          <IstDateTimeField
            id="offer-starts"
            legend="Starts"
            value={form.starts}
            onChange={(starts) => set({ starts })}
            error={
              (checked ? problems.starts : null) ??
              (apiErrors.starts_at ? { field: "date", message: apiErrors.starts_at } : null)
            }
            hint="Empty: as soon as it is switched on. A date without a time starts at midnight."
          />
          <IstDateTimeField
            id="offer-ends"
            legend="Ends"
            value={form.ends}
            onChange={(ends) => set({ ends })}
            error={
              (checked ? problems.ends : null) ??
              (apiErrors.ends_at ? { field: "date", message: apiErrors.ends_at } : null)
            }
            hint="A date without a time lasts the whole day (until 11:59 pm)."
          />
          <NumberField
            id="offer-priority"
            label="Priority (0–1000)"
            value={form.priority}
            onValueChange={(priority) => set({ priority })}
            error={errors.priority}
            hint="When several offers are live in one place, the highest shows first."
            className="max-w-60"
          />
          <Checkbox
            checked={form.is_active}
            onChange={(event) => set({ is_active: event.target.checked })}
            label="Switched on: show it between its dates"
            error={errors.is_active}
          />
        </fieldset>
        <div className="flex flex-wrap gap-2.5">
          <Button type="submit" loading={busy} disabled={offer !== null && !dirty}>
            {offer ? "Save offer" : "Add offer"}
          </Button>
          <Button variant="secondary" disabled={busy} onClick={onClose}>
            Close
          </Button>
          {offer && !offer.has_been_live ? (
            <Button variant="danger" disabled={busy} onClick={() => setDeleting(true)}>
              Delete
            </Button>
          ) : null}
        </div>
        {offer?.has_been_live ? (
          <p className="text-caption text-muted">
            This offer has been on the website, so it is kept for the record. Switch it off or let
            it end instead.
          </p>
        ) : null}
      </form>
      <ConfirmDialog
        open={deleting}
        title="Delete this offer?"
        confirmLabel="Delete offer"
        tone="danger"
        busy={busy}
        error={deleteError}
        onCancel={() => setDeleting(false)}
        onConfirm={() => void remove()}
      >
        It was never on the website, so it can be deleted for good. This can&apos;t be undone.
      </ConfirmDialog>
    </section>
  );
}
