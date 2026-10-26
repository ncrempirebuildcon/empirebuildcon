"use client";
/**
 * Media fields for content forms: one photo or video (`MediaField`: a block's image, a post
 * cover, an offer image, a testimonial photo) or an ordered set of photos (`GalleryField`: the
 * gallery block, up to 24). Staff choose from the library (LibraryPicker.tsx) or upload a new
 * file straight into the library (SlotUploader with no attach target, as the SEO share image
 * does, part 2). The chosen id is saved by the caller's own form.
 *
 * WHY library ids and not media links: content rows keep a media id in their own field (the
 * contract's `cover_media_id`, `image_media_id`, block `data`), and the API refuses to delete a
 * library item while anything uses it, so a choice can't end up pointing at a missing file.
 *
 * Honest labels (review L11; DESIGN_SYSTEM §7): where the website shows a photo with its label
 * (block photos, post covers, offer images: `labelRequired`), an upload asks for the label first,
 * and a library photo without one opens its details to add one before it is used. Someone
 * without `media.upload` can't label it, so the field says so instead of using it. Sample tiles
 * are exempt (never public, D-015); testimonial photos are exempt (a person, not a property).
 *
 * Accessibility: each field is a labelled group; the preview image has the item's alt text; the
 * buttons name the field ("Choose Cover image from the library"); the gallery's order uses
 * ReorderButtons with an announcement, like every other ordered list in the CMS.
 */
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Button, LiveRegion, ReorderButtons, moveAnnouncement, moveItem } from "@empire/ui";
import { honestLabelText } from "@/lib/media/labels";
import type { Media } from "@/lib/media/upload";
import { LibraryPicker, type PickableKind } from "./LibraryPicker";
import { MediaDetailsDialog } from "./MediaDetailsDialog";
import { MediaThumb, altFor } from "./MediaThumb";
import { SlotUploader } from "./SlotUploader";

const NOUN: Record<PickableKind, string> = { image: "photo", video: "video" };

export interface MediaFieldProps {
  /** Visible label, e.g. "Cover image". */
  label: string;
  kind: PickableKind;
  /** The chosen item, or null. */
  value: Media | null;
  onChange: (media: Media | null) => void;
  /** With `media.upload`: offer "Upload a photo" next to "Choose from the library". */
  canUpload: boolean;
  /** Read-only (no write permission): shows the choice without buttons. */
  disabled?: boolean;
  error?: string;
  hint?: ReactNode;
  /** Id prefix for the group and its upload button. */
  id: string;
  /** Called with true while a file is being sent (for the leave warning). */
  onBusyChange?: (busy: boolean) => void;
  /** An item is chosen but its details aren't loaded, so there is no preview to show. */
  missingPreview?: boolean;
  /** The website shows this photo with its honest label, so it must have one (see above). */
  labelRequired?: boolean;
}

/** True when this photo can't be used where a label is required (sample tiles are exempt). */
export const needsLabel = (media: Media) =>
  media.kind === "image" && !media.label && !media.is_sample;

export function MediaField({
  label,
  kind,
  value,
  onChange,
  canUpload,
  disabled = false,
  error,
  hint,
  id,
  onBusyChange,
  missingPreview = false,
  labelRequired = false,
}: MediaFieldProps) {
  const [picking, setPicking] = useState(false);
  // A library photo with no label, waiting in its details dialog before it is used.
  const [labelling, setLabelling] = useState<Media | null>(null);
  const [labelProblem, setLabelProblem] = useState<string | null>(null);
  const noun = NOUN[kind];
  const askLabel = labelRequired && kind === "image";

  function choose(media: Media) {
    setLabelProblem(null);
    if (!askLabel || !needsLabel(media)) {
      onChange(media);
      return;
    }
    if (canUpload) setLabelling(media);
    else
      setLabelProblem(
        `“${media.title}” has no honest label yet, so it can't be used here. Ask someone who uploads media to label it in the media library.`,
      );
  }
  const labelId = `${id}-label`;
  const shownError = error ?? labelProblem ?? undefined;
  const describedBy = [hint ? `${id}-hint` : null, shownError ? `${id}-error` : null]
    .filter(Boolean)
    .join(" ");
  const honest = value ? honestLabelText(value.label, value.label_month) : null;

  return (
    <div
      role="group"
      aria-labelledby={labelId}
      aria-describedby={describedBy || undefined}
      className="flex min-w-0 flex-col gap-2"
    >
      <span id={labelId} className="text-small font-semibold text-ivory">
        {label}
      </span>
      {value ? (
        <div className="flex flex-wrap items-center gap-3">
          <MediaThumb
            media={value}
            shape={kind === "video" ? "video" : "photo"}
            className="w-40 shrink-0 rounded-tag border border-line-strong"
          />
          <span className="flex min-w-0 flex-[1_1_160px] flex-col gap-0.5 text-caption">
            <span className="font-semibold [overflow-wrap:anywhere] text-ivory">{value.title}</span>
            {kind === "image" ? (
              <span className={honest ? "text-body" : "text-danger"}>
                {honest ??
                  (askLabel && needsLabel(value)
                    ? "No honest label yet: it can't be saved here until it has one."
                    : "No honest label yet: add one in the media library.")}
              </span>
            ) : null}
            <span className="text-muted">Alt text: {altFor(value)}</span>
          </span>
        </div>
      ) : (
        <p className="rounded-tile border border-dashed border-line-strong bg-noir-700 px-3.5 py-3 text-caption text-muted">
          {missingPreview
            ? `A ${noun} is chosen, but its preview can't be shown here. Choose it again to see it.`
            : `No ${noun} chosen.`}
        </p>
      )}
      {hint ? (
        <div id={`${id}-hint`} className="text-caption text-muted">
          {hint}
        </div>
      ) : null}
      {shownError ? (
        <p id={`${id}-error`} className="text-caption text-danger">
          {shownError}
        </p>
      ) : null}
      {disabled ? null : (
        <div className="flex flex-wrap items-start gap-2">
          <Button
            variant="secondary"
            aria-label={
              value || missingPreview ? `Change ${label}` : `Choose from the library: ${label}`
            }
            onClick={() => setPicking(true)}
          >
            {value || missingPreview ? "Change" : "Choose from the library"}
          </Button>
          {value && askLabel && needsLabel(value) && canUpload ? (
            <Button
              variant="secondary"
              aria-label={`Add an honest label: ${label}`}
              onClick={() => setLabelling(value)}
            >
              Add a label
            </Button>
          ) : null}
          {canUpload ? (
            <SlotUploader
              id={`${id}-upload`}
              variant="secondary"
              target={null}
              askPhotoLabel={askLabel}
              kinds={[kind]}
              destination={`the library; it is used as the ${label.toLowerCase()} when you save`}
              aria-label={`Upload a ${noun} for ${label}`}
              onUploaded={(media) => onChange(media)}
              onBusyChange={onBusyChange}
            >
              {`Upload a ${noun}`}
            </SlotUploader>
          ) : null}
          {value || missingPreview ? (
            <Button
              variant="tertiary"
              className="min-h-11"
              aria-label={`Remove ${label}`}
              onClick={() => onChange(null)}
            >
              Remove
            </Button>
          ) : null}
        </div>
      )}
      <LibraryPicker
        open={picking}
        kind={kind}
        chosenIds={value ? [value.id] : []}
        onClose={() => setPicking(false)}
        onPick={([media]) => {
          setPicking(false);
          if (media) choose(media);
        }}
      />
      <MediaDetailsDialog
        media={labelling}
        labelRequired
        intro={`The website shows this photo with its honest label, so say what it is before it is used as the ${label.toLowerCase()}.`}
        onClose={() => setLabelling(null)}
        onSaved={(saved) => onChange(saved)}
      />
    </div>
  );
}

export interface GalleryFieldProps {
  label: string;
  /** The photos in display order. */
  value: readonly Media[];
  onChange: (items: Media[]) => void;
  /** Most photos allowed (the gallery block takes 24). */
  max: number;
  canUpload: boolean;
  disabled?: boolean;
  error?: string;
  id: string;
  onBusyChange?: (busy: boolean) => void;
  /** Uploads ask for the honest label first (the gallery block's photos need one). */
  labelRequired?: boolean;
}

/** An ordered set of library photos with Add, Move up/down and Remove. */
export function GalleryField({
  label,
  value,
  onChange,
  max,
  canUpload,
  disabled = false,
  error,
  id,
  onBusyChange,
  labelRequired = false,
}: GalleryFieldProps) {
  const [picking, setPicking] = useState(false);
  const [message, setMessage] = useState("");
  const labelId = useId();
  const full = value.length >= max;
  // WHY a ref: a batch of uploads finishes one file at a time, each calling `add` before the
  // parent re-renders; the ref keeps every file instead of the last one winning.
  const latest = useRef(value);
  useEffect(() => {
    latest.current = value;
  }, [value]);

  function move(from: number, to: number) {
    const item = value[from];
    if (!item) return;
    onChange(moveItem(value, from, to));
    setMessage(moveAnnouncement(item.title, to, value.length));
  }

  function add(items: readonly Media[]) {
    const current = latest.current;
    const known = new Set(current.map((media) => media.id));
    const next = [...current, ...items.filter((media) => !known.has(media.id))].slice(0, max);
    latest.current = next;
    onChange(next);
    setMessage(`${next.length - current.length} added. ${next.length} of ${max} photos.`);
  }

  return (
    <div
      role="group"
      aria-labelledby={labelId}
      aria-describedby={error ? `${id}-error` : undefined}
      className="flex min-w-0 flex-col gap-2"
    >
      <span id={labelId} className="text-small font-semibold text-ivory">
        {label} · {value.length} of {max}
      </span>
      {value.length === 0 ? (
        <p className="rounded-tile border border-dashed border-line-strong bg-noir-700 px-3.5 py-3 text-caption text-muted">
          No photos yet.
        </p>
      ) : (
        <ol aria-label={`${label} in display order`} className="flex flex-col gap-2">
          {value.map((media, index) => (
            <li
              key={media.id}
              className="flex flex-wrap items-center gap-3 rounded-tile border border-line bg-noir-900 p-2"
            >
              <MediaThumb media={media} className="w-24 shrink-0 rounded-tag" />
              <span className="min-w-0 flex-[1_1_120px] text-caption [overflow-wrap:anywhere] text-ivory">
                {media.title}
                <span className="block text-muted">
                  {honestLabelText(media.label, media.label_month) ?? "No honest label yet"}
                </span>
              </span>
              {disabled ? null : (
                <span className="flex flex-wrap gap-1">
                  <ReorderButtons
                    index={index}
                    count={value.length}
                    itemLabel={media.title}
                    onMove={move}
                  />
                  <Button
                    variant="tertiary"
                    className="min-h-11"
                    aria-label={`Remove ${media.title} from ${label}`}
                    onClick={() => {
                      onChange(value.filter((other) => other.id !== media.id));
                      setMessage(`${media.title} removed.`);
                    }}
                  >
                    Remove
                  </Button>
                </span>
              )}
            </li>
          ))}
        </ol>
      )}
      {error ? (
        <p id={`${id}-error`} className="text-caption text-danger">
          {error}
        </p>
      ) : null}
      {disabled ? null : (
        <div className="flex flex-wrap items-start gap-2">
          <Button
            variant="secondary"
            disabled={full}
            aria-label={`Add from the library: ${label}`}
            onClick={() => setPicking(true)}
          >
            Add from the library
          </Button>
          {canUpload ? (
            <SlotUploader
              id={`${id}-upload`}
              variant="secondary"
              target={null}
              kinds={["image"]}
              askPhotoLabel={labelRequired}
              multiple
              disabled={full}
              destination="the library and this gallery"
              aria-label={`Upload photos for ${label}`}
              onUploaded={(media) => add([media])}
              onBusyChange={onBusyChange}
            >
              Upload photos
            </SlotUploader>
          ) : null}
        </div>
      )}
      {full ? <p className="text-caption text-muted">The gallery is full ({max} photos).</p> : null}
      <LiveRegion message={message} />
      <LibraryPicker
        open={picking}
        kind="image"
        multiple
        max={max}
        chosenIds={value.map((media) => media.id)}
        onClose={() => setPicking(false)}
        onPick={(items) => {
          setPicking(false);
          add(items);
        }}
      />
    </div>
  );
}
