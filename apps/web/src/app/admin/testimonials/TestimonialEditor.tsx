"use client";
/**
 * Add or edit one testimonial (board NoirCmsContent, "Add a testimonial"): the buyer's name as
 * they agreed to be shown, their words unedited, the project, where it came from, the date they
 * agreed to publishing, an optional rating and photo, and "Show on the website".
 *
 * COMPLIANCE (AGENTS.md "Honest content"; spec Phase 4 part 4 §6): "Show on the website" stays
 * disabled until the source and the consent date are filled in; the API refuses it otherwise
 * (and a consent date in the future). Deleting is always possible, e.g. when a buyer withdraws
 * consent: it also leaves every page block that showed it.
 *
 * WHY no "permission document" upload (the board shows one): the API has no private file field
 * for it. The consent date and source are what the website relies on; the signed form stays in
 * the owner's records (TODO(phase-5): revisit if the owner wants it in the CMS).
 */
import { useEffect, useState } from "react";
import { Alert, Button, Checkbox, ConfirmDialog, Select, TextField, Textarea } from "@empire/ui";
import { istToday } from "@empire/ui/format";
import { api, call, type Schema } from "@/lib/api";
import { isHttpsUrl } from "@/lib/content/links";
import type { Media } from "@/lib/media/upload";
import { fieldErrors, problemMessage, type FieldErrors } from "@/lib/problems";
import { MediaField } from "@/components/admin/media/MediaField";
import { useLoad } from "@/components/admin/useLoad";
import { useAdminSession } from "../session-context";

type Testimonial = Schema<"Testimonial">;

interface TestimonialForm {
  person_name: string;
  person_detail: string;
  quote: string;
  project_id: string;
  source: string;
  source_url: string;
  consent_date: string;
  rating: string;
  photo: Media | null;
  is_visible: boolean;
}

const EMPTY: TestimonialForm = {
  person_name: "",
  person_detail: "",
  quote: "",
  project_id: "",
  source: "",
  source_url: "",
  consent_date: "",
  rating: "",
  photo: null,
  is_visible: false,
};

/** Suggested ways a testimonial reaches Empire (board NoirCmsContent's source list). */
const SOURCE_SUGGESTIONS = [
  "Written feedback form",
  "Email from the buyer",
  "Google review",
  "Video",
];

function toForm(t: Testimonial): TestimonialForm {
  return {
    person_name: t.person_name,
    person_detail: t.person_detail ?? "",
    quote: t.quote,
    project_id: t.project_id ?? "",
    source: t.source,
    source_url: t.source_url ?? "",
    consent_date: t.consent_date ?? "",
    rating: t.rating ? String(t.rating) : "",
    photo: t.photo ?? null,
    is_visible: t.is_visible,
  };
}

const orNull = (value: string) => (value.trim() === "" ? null : value.trim());

function toInput(form: TestimonialForm): Schema<"TestimonialInput"> {
  return {
    person_name: form.person_name.trim(),
    person_detail: orNull(form.person_detail),
    quote: form.quote.trim(),
    project_id: form.project_id || null,
    source: form.source.trim(),
    source_url: orNull(form.source_url),
    consent_date: form.consent_date || null,
    rating: form.rating ? Number(form.rating) : null,
    photo_media_id: form.photo?.id ?? null,
    is_visible: form.is_visible,
  };
}

function check(form: TestimonialForm): FieldErrors {
  const out: FieldErrors = {};
  if (!form.person_name.trim()) out.person_name = "Enter the name the buyer agreed to show.";
  if (!form.quote.trim()) out.quote = "Paste the exact words the buyer approved.";
  if (form.source.trim().length < 3)
    out.source = "Say where it came from, e.g. written feedback form, 2 Mar 2026.";
  if (form.source_url.trim() && !isHttpsUrl(form.source_url.trim())) {
    out.source_url = "Use a full https:// address.";
  }
  if (form.consent_date && form.consent_date > istToday()) {
    out.consent_date = "The consent date can't be in the future.";
  }
  if (form.is_visible && (!form.source.trim() || !form.consent_date)) {
    out.is_visible = "Record the source and the consent date before showing it.";
  }
  return out;
}

export interface TestimonialEditorProps {
  testimonial: Testimonial | null;
  onDirtyChange: (dirty: boolean) => void;
  onSaved: (saved: Testimonial | null, message: string) => Promise<void>;
  onClose: () => void;
}

export function TestimonialEditor({
  testimonial,
  onDirtyChange,
  onSaved,
  onClose,
}: TestimonialEditorProps) {
  const { can } = useAdminSession();
  const start = testimonial ? toForm(testimonial) : EMPTY;
  const [form, setFormState] = useState<TestimonialForm>(start);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const projects = useLoad("testimonial-projects", () =>
    call(api.GET("/api/v1/admin/projects", { params: { query: { per_page: 100 } } })),
  );

  const dirty = JSON.stringify(toInput(form)) !== JSON.stringify(toInput(start));
  useEffect(() => {
    onDirtyChange(dirty || uploading);
  }, [dirty, uploading, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);

  const set = (patch: Partial<TestimonialForm>) =>
    setFormState((current) => {
      const next = { ...current, ...patch };
      // Showing switches itself off when its conditions go away, so it never looks on but locked.
      if (!next.source.trim() || !next.consent_date) next.is_visible = false;
      return next;
    });
  const canShow = form.source.trim().length >= 3 && Boolean(form.consent_date);

  async function save() {
    if (busy) return;
    const found = check(form);
    if (Object.keys(found).length > 0) {
      setErrors(found);
      setError("Some fields need attention.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const body = toInput(form);
      const saved = testimonial
        ? await call(
            api.PATCH("/api/v1/admin/testimonials/{id}", {
              params: { path: { id: testimonial.id } },
              body,
            }),
          )
        : await call(api.POST("/api/v1/admin/testimonials", { body }));
      setErrors({});
      onDirtyChange(false);
      await onSaved(
        saved,
        saved.is_visible
          ? `Saved. ${saved.person_name}'s testimonial is shown on the website.`
          : `Saved. ${saved.person_name}'s testimonial is not shown on the website yet.`,
      );
    } catch (err) {
      setErrors(fieldErrors(err));
      setError(problemMessage(err, "Couldn't save the testimonial."));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!testimonial) return;
    setBusy(true);
    setDeleteError(null);
    try {
      await call(
        api.DELETE("/api/v1/admin/testimonials/{id}", { params: { path: { id: testimonial.id } } }),
      );
      onDirtyChange(false);
      setDeleting(false);
      await onSaved(null, "The testimonial was deleted and removed from every page.");
    } catch (err) {
      setDeleteError(problemMessage(err, "Couldn't delete the testimonial."));
    } finally {
      setBusy(false);
    }
  }

  const title = testimonial ? "Edit testimonial" : "Add a testimonial";
  return (
    <section
      aria-labelledby="testimonial-editor-title"
      className="flex min-w-0 flex-[1_1_360px] flex-col gap-4 rounded-card border border-gold-line-strong bg-noir-800 p-4"
    >
      <h2 id="testimonial-editor-title" className="text-[17px] font-bold">
        {title}
      </h2>
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
            id="testimonial-name"
            label="Buyer's name, as they agreed to be shown"
            required
            maxLength={80}
            value={form.person_name}
            placeholder="[e.g. first name and city]"
            onChange={(event) => set({ person_name: event.target.value })}
            error={errors.person_name}
          />
          <TextField
            id="testimonial-detail"
            label="Detail (optional)"
            maxLength={120}
            value={form.person_detail}
            placeholder="[e.g. bought in 2025, Tower B]"
            onChange={(event) => set({ person_detail: event.target.value })}
            error={errors.person_detail}
          />
          <Select
            id="testimonial-project"
            label="Project (optional)"
            value={form.project_id}
            placeholder={projects.loading ? "Loading projects…" : "No project"}
            options={(projects.data?.items ?? []).map((p) => ({ value: p.id, label: p.name }))}
            onChange={(event) => set({ project_id: event.target.value })}
            error={errors.project_id}
          />
          <Textarea
            id="testimonial-quote"
            label="Their words, unedited"
            required
            rows={4}
            maxLength={1500}
            value={form.quote}
            placeholder="[Paste the exact text the buyer approved]"
            onChange={(event) => set({ quote: event.target.value })}
            error={errors.quote}
          />
          <TextField
            id="testimonial-source"
            label="Where it came from"
            required
            maxLength={160}
            list="testimonial-sources"
            value={form.source}
            placeholder="[e.g. Written feedback form, 2 Mar 2026]"
            onChange={(event) => set({ source: event.target.value })}
            error={errors.source}
          />
          <datalist id="testimonial-sources">
            {SOURCE_SUGGESTIONS.map((source) => (
              <option key={source} value={source} />
            ))}
          </datalist>
          <TextField
            id="testimonial-source-url"
            label="Source link (optional)"
            maxLength={500}
            value={form.source_url}
            placeholder="https://…"
            onChange={(event) => set({ source_url: event.target.value.trim() })}
            error={errors.source_url}
            hint="E.g. the review or video, if it is public."
          />
          <TextField
            id="testimonial-consent"
            label="Date the buyer agreed in writing to publishing"
            type="date"
            max={istToday()}
            value={form.consent_date}
            onChange={(event) => set({ consent_date: event.target.value })}
            error={errors.consent_date}
            hint="Needed before it can be shown on the website."
            className="max-w-72"
          />
          <Select
            id="testimonial-rating"
            label="Rating (optional)"
            value={form.rating}
            placeholder="No rating"
            options={[1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: `${n} of 5` }))}
            onChange={(event) => set({ rating: event.target.value })}
            error={errors.rating}
            className="max-w-60"
          />
          {/* WHY no labelRequired: the photo shows the person, not a property (review L11). */}
          <MediaField
            id="testimonial-photo"
            label="Photo (optional)"
            kind="image"
            value={form.photo}
            onChange={(photo) => set({ photo })}
            canUpload={can("media.upload")}
            error={errors.photo_media_id}
            hint="Only with the buyer's permission for the photo too."
            onBusyChange={setUploading}
          />
          <Checkbox
            checked={form.is_visible}
            disabled={!canShow}
            onChange={(event) => set({ is_visible: event.target.checked })}
            label="Show on the website"
            error={errors.is_visible}
            hint={
              canShow
                ? "The website shows the source next to the words."
                : "Locked until the source and the consent date are filled in."
            }
          />
        </fieldset>
        <div className="flex flex-wrap gap-2.5">
          <Button type="submit" loading={busy} disabled={testimonial !== null && !dirty}>
            {testimonial ? "Save testimonial" : "Add testimonial"}
          </Button>
          <Button variant="secondary" disabled={busy} onClick={onClose}>
            Close
          </Button>
          {testimonial ? (
            <Button variant="danger" disabled={busy} onClick={() => setDeleting(true)}>
              Delete
            </Button>
          ) : null}
        </div>
      </form>
      <ConfirmDialog
        open={deleting}
        title="Delete this testimonial?"
        confirmLabel="Delete testimonial"
        tone="danger"
        busy={busy}
        error={deleteError}
        onCancel={() => setDeleting(false)}
        onConfirm={() => void remove()}
      >
        It is removed from the website and from every page that shows it. Use this when a buyer
        withdraws consent. This can&apos;t be undone.
      </ConfirmDialog>
    </section>
  );
}
