"use client";
/**
 * "Photo details" / "Video details" / "Document details": rename, alt text and the honest label
 * (with its month for progress photos), saved with PATCH /admin/media/{id}. Used by every media
 * list in the project editor and by the library page.
 *
 * WHY a dialog and not inputs on each card: a card in the photo grid is 176 px wide; title, alt
 * text, label and month don't fit there legibly, and one explicit "Save details" avoids
 * half-saved edits on every keystroke or blur.
 *
 * WHY month and year selects: `<input type="month">` falls back to a plain text box in Safari
 * and Firefox, where staff would have to guess the format.
 *
 * COMPLIANCE: a progress photo needs its month (the API refuses one without); an actual photo may
 * have one; an artist's impression never does. The label is never filled in for the user
 * (lib/media/labels.ts).
 */
import { useState, type ReactNode } from "react";
import { Alert, Button, Dialog, Select, TextField, Textarea } from "@empire/ui";
import { api, call } from "@/lib/api";
import { DATED_LABELS, HONEST_LABEL, firstOfMonth, type HonestLabel } from "@/lib/media/labels";
import type { Media } from "@/lib/media/upload";
import { fieldErrors, problemMessage, type FieldErrors } from "@/lib/problems";
import { keyOf, optionsOf } from "@/lib/labels";
import { MediaThumb } from "./MediaThumb";
import { MonthPicker, monthProblem } from "./MonthPicker";

const NOUN: Record<Media["kind"], string> = {
  image: "Photo",
  video: "Video",
  document: "Document",
};

interface Draft {
  title: string;
  alt_text: string;
  label: HonestLabel | "";
  month: string;
  year: string;
}

function toDraft(media: Media): Draft {
  const [year, month] = (media.label_month ?? "").split("-");
  return {
    title: media.title,
    alt_text: media.alt_text ?? "",
    label: media.label ?? "",
    month: month ? String(Number(month)) : "",
    year: year ?? "",
  };
}

export interface MediaDetailsDialogProps {
  /** The item being edited, or null when the dialog is closed. */
  media: Media | null;
  onClose: () => void;
  /** Called with the saved item. */
  onSaved: (media: Media) => Promise<unknown> | void;
  /** A sentence above the fields saying why the dialog opened (e.g. a label is needed). */
  intro?: ReactNode;
  /** A photo must leave with an honest label (where the website shows it with one; L11). */
  labelRequired?: boolean;
}

export function MediaDetailsDialog({ media, ...rest }: MediaDetailsDialogProps) {
  return (
    <>
      {/* WHY keyed: each item opens with a fresh draft taken from its saved values. */}
      {media ? <DetailsForm key={media.id} media={media} {...rest} /> : null}
    </>
  );
}

function DetailsForm({
  media,
  onClose,
  onSaved,
  intro,
  labelRequired = false,
}: Omit<MediaDetailsDialogProps, "media"> & { media: Media }) {
  const [draft, setDraftState] = useState<Draft>(() => toDraft(media));
  const [errors, setErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const set = (patch: Partial<Draft>) => setDraftState((current) => ({ ...current, ...patch }));
  const isImage = media.kind === "image";
  const noun = NOUN[media.kind];
  const dated = draft.label !== "" && DATED_LABELS.has(draft.label);
  const monthRequired = draft.label === "progress_photo";

  function validate(): FieldErrors {
    const found: FieldErrors = {};
    if (!draft.title.trim()) found.title = `Give the ${noun.toLowerCase()} a title.`;
    if (isImage && labelRequired && !draft.label) found.label = "Choose what this photo is.";
    const month = dated ? monthProblem(draft.month, draft.year, monthRequired) : null;
    if (month) found.label_month = month;
    return found;
  }

  async function save() {
    if (saving) return;
    const found = validate();
    if (Object.keys(found).length > 0) {
      setErrors(found);
      setError("Some fields need attention.");
      return;
    }
    setSaving(true);
    setErrors({});
    setError(null);
    try {
      const saved = await call(
        api.PATCH("/api/v1/admin/media/{id}", {
          params: { path: { id: media.id } },
          body: {
            title: draft.title.trim(),
            alt_text: draft.alt_text.trim() || null,
            ...(isImage
              ? {
                  label: draft.label || null,
                  label_month:
                    dated && draft.month && draft.year
                      ? firstOfMonth(Number(draft.year), Number(draft.month))
                      : null,
                }
              : {}),
          },
        }),
      );
      await onSaved(saved);
      onClose();
    } catch (err) {
      setErrors(fieldErrors(err));
      setError(problemMessage(err, `Couldn't save the ${noun.toLowerCase()}'s details.`));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open
      wide
      title={`${noun} details`}
      busy={saving}
      onClose={onClose}
      onSubmit={() => void save()}
      footer={
        <>
          <Button variant="secondary" disabled={saving} onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={saving}>
            Save details
          </Button>
        </>
      }
    >
      <div className="flex flex-wrap gap-4">
        <div className="w-40 shrink-0">
          <MediaThumb media={media} className="w-full rounded-tile" />
        </div>
        <fieldset disabled={saving} className="flex min-w-0 flex-[1_1_260px] flex-col gap-4">
          <legend className="sr-only">{`${noun} details`}</legend>
          {intro ? <p className="text-small">{intro}</p> : null}
          {error ? <Alert tone="error">{error}</Alert> : null}
          <TextField
            label="Title"
            required
            maxLength={160}
            value={draft.title}
            onChange={(e) => set({ title: e.target.value })}
            error={errors.title}
            hint="Shown in the CMS and, for documents, on the download button."
          />
          {media.kind !== "document" ? (
            <Textarea
              label="Alt text"
              rows={2}
              maxLength={250}
              value={draft.alt_text}
              onChange={(e) => set({ alt_text: e.target.value })}
              error={errors.alt_text}
              hint="What the image shows, for people who can't see it, e.g. Tower A from the main road at dusk. Leave empty to use the title."
            />
          ) : null}
          {isImage ? (
            <>
              <Select
                label="Honest label"
                required={labelRequired}
                value={draft.label}
                placeholder="Not labelled yet"
                options={optionsOf(HONEST_LABEL)}
                onChange={(e) => set({ label: keyOf(HONEST_LABEL, e.target.value, "") })}
                error={errors.label}
                hint="Shown with the image on the website. Renders are always an artist's impression."
              />
              {dated ? (
                <MonthPicker
                  month={draft.month}
                  year={draft.year}
                  onChange={set}
                  required={monthRequired}
                  error={errors.label_month}
                />
              ) : null}
            </>
          ) : null}
        </fieldset>
      </div>
    </Dialog>
  );
}
