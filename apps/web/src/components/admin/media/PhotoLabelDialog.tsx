"use client";
/**
 * "What are these photos?": asked before a batch of photos uploads to the project's photo list
 * (Media tab). The answer (artist's impression, actual photo, or progress photo with its month)
 * is sent with every photo in the batch (`ImageUpload.label` / `label_month`), so they attach
 * visible; each one can still be changed later in Edit details.
 *
 * COMPLIANCE: honest labels (DESIGN_SYSTEM §7, handbook README "Honest content"). The API keeps a
 * gallery photo hidden until it has a label, so this question is how photos reach the website.
 * Nothing is pre-selected: the CMS never guesses whether an image is a render or a photo.
 */
import { useState } from "react";
import { Alert, Button, Dialog } from "@empire/ui";
import { HONEST_LABEL, firstOfMonth, type HonestLabel } from "@/lib/media/labels";
import { MonthPicker, monthProblem } from "./MonthPicker";
import type { PhotoLabel } from "./useUploads";

const CHOICES: { value: HonestLabel; help: string }[] = [
  {
    value: "artist_impression",
    help: "A render or illustration, not a photo of the real building.",
  },
  { value: "actual_photo", help: "A photo of the real building, site or show flat." },
  { value: "progress_photo", help: "A construction photo; say which month it shows." },
];

export interface PhotoLabelDialogProps {
  /** The photos waiting for an answer, or null when the dialog is closed. */
  files: readonly File[] | null;
  onCancel: () => void;
  onConfirm: (label: PhotoLabel) => void;
}

export function PhotoLabelDialog({ files, onCancel, onConfirm }: PhotoLabelDialogProps) {
  // WHY keyed by the batch: every batch starts with nothing chosen.
  return files && files.length > 0 ? (
    <LabelForm
      key={files.map((f) => f.name).join("|")}
      files={files}
      onCancel={onCancel}
      onConfirm={onConfirm}
    />
  ) : null;
}

function LabelForm({
  files,
  onCancel,
  onConfirm,
}: {
  files: readonly File[];
  onCancel: () => void;
  onConfirm: (label: PhotoLabel) => void;
}) {
  const [label, setLabel] = useState<HonestLabel | "">("");
  const [month, setMonth] = useState("");
  const [year, setYear] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [monthError, setMonthError] = useState<string | undefined>();
  const count = files.length;
  const noun = count === 1 ? "photo" : "photos";
  const dated = label === "actual_photo" || label === "progress_photo";

  function confirm() {
    if (!label) {
      setError(`Choose what ${count === 1 ? "this photo is" : "these photos are"}.`);
      return;
    }
    const problem = dated ? monthProblem(month, year, label === "progress_photo") : null;
    if (problem) {
      setMonthError(problem);
      setError("Some fields need attention.");
      return;
    }
    onConfirm({
      label,
      labelMonth: dated && month && year ? firstOfMonth(Number(year), Number(month)) : undefined,
    });
  }

  return (
    <Dialog
      open
      title={`What ${count === 1 ? "is this photo" : `are these ${count} photos`}?`}
      onClose={onCancel}
      onSubmit={confirm}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit">{`Upload ${count} ${noun}`}</Button>
        </>
      }
    >
      <p className="text-small">
        Every image on the website says what it is. Your answer is saved with{" "}
        {count === 1 ? "the photo" : `all ${count} photos`}; you can change each one later in Edit
        details.
      </p>
      <ul className="flex flex-col gap-0.5 text-caption text-muted">
        {files.slice(0, 5).map((file) => (
          <li key={file.name} className="[overflow-wrap:anywhere]">
            {file.name}
          </li>
        ))}
        {count > 5 ? <li>and {count - 5} more</li> : null}
      </ul>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1.5 text-small font-semibold text-ivory">
          Honest label <span className="font-normal text-muted">(required)</span>
        </legend>
        {CHOICES.map((choice) => (
          <label
            key={choice.value}
            className="flex min-h-11 cursor-pointer items-start gap-2.5 rounded-tile border border-line px-3 py-2.5 has-checked:border-gold-500"
          >
            <input
              type="radio"
              name="photo-label"
              value={choice.value}
              checked={label === choice.value}
              onChange={() => {
                setLabel(choice.value);
                setError(null);
              }}
              data-autofocus={choice.value === "artist_impression" ? true : undefined}
              className="mt-0.5 size-5 shrink-0 accent-gold-500"
            />
            <span className="flex flex-col">
              <span className="text-small font-bold text-ivory">{HONEST_LABEL[choice.value]}</span>
              <span className="text-caption text-muted">{choice.help}</span>
            </span>
          </label>
        ))}
      </fieldset>
      {dated ? (
        <MonthPicker
          month={month}
          year={year}
          onChange={(next) => {
            if (next.month !== undefined) setMonth(next.month);
            if (next.year !== undefined) setYear(next.year);
            setMonthError(undefined);
          }}
          required={label === "progress_photo"}
          error={monthError}
        />
      ) : null}
    </Dialog>
  );
}
