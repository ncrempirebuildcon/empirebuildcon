"use client";
/**
 * One upload button for one place: the RERA QR code, the brochure, a configuration's floor plan,
 * an update's progress photos, the share image. The chosen file is checked, sent (with progress
 * and Cancel underneath) and attached to `target`; `onUploaded` then runs (e.g. re-read the
 * project).
 *
 * For single-valued roles (brochure, rera_qr, hero, og_image, floor_plan) the API replaces the
 * old link in the same transaction, so "Replace" is just another upload; the old file stays in
 * the library.
 *
 * With `askPhotoLabel`, photos wait for the honest-label question (PhotoLabelDialog) and upload
 * with the answer, for places the website shows a photo with its label (block photos, post
 * covers, offer images; review L11). COMPLIANCE: nothing is pre-selected.
 */
import { useEffect, useState } from "react";
import { FileButton, type ButtonVariant } from "@empire/ui";
import { acceptFor, type MediaKind } from "@/lib/media/files";
import type { ImageEncoding } from "@/lib/media/resize";
import type { AttachTarget, Media } from "@/lib/media/upload";
import { PhotoLabelDialog } from "./PhotoLabelDialog";
import { UploadQueue } from "./UploadQueue";
import { useUploads, type PhotoLabel } from "./useUploads";

export interface SlotUploaderProps {
  /** Where the file is attached; null keeps it in the library only. */
  target: AttachTarget | null;
  /** Kinds accepted here, e.g. ["image"] for the QR code, ["image", "document"] for plans. */
  kinds: readonly MediaKind[];
  /** Narrower chooser filter, e.g. PDF only for the brochure. */
  accept?: string;
  /** The matching rule for `accept` (the chooser filter can be bypassed): a refusal, or null. */
  extraCheck?: (file: File) => string | null;
  /** Allow several files (progress photos). */
  multiple?: boolean;
  /** How photos are encoded: "photo" (default), "qr" (lossless, 1200 px) or "plan" (lossless). */
  encoding?: ImageEncoding;
  /** The honest label saved with each photo (progress photos of a dated update). */
  photoLabel?: PhotoLabel;
  /** Ask for the honest label before photos upload (when `photoLabel` isn't given). */
  askPhotoLabel?: boolean;
  /** Re-reads the owner after a cancel that may have raced the save (useUploads step 5). */
  reconcile?: () => Promise<unknown>;
  /** Button text, e.g. "Upload QR image". */
  children: string;
  /** Fuller name for screen readers, e.g. "Add floor plan for 2 BHK Classic". */
  "aria-label"?: string;
  /** Words for the success message, e.g. "the RERA QR code". */
  destination: string;
  /** Runs after each saved upload. */
  onUploaded: (media: Media, kind: MediaKind) => Promise<unknown> | void;
  variant?: ButtonVariant;
  disabled?: boolean;
  id?: string;
  className?: string;
  /** Called with true while files are being sent (for the leave warning). */
  onBusyChange?: (busy: boolean) => void;
}

export function SlotUploader(props: SlotUploaderProps) {
  const uploads = useUploads({
    plan: {
      kinds: props.kinds,
      targetFor: () => props.target,
      encoding: props.encoding,
      photoLabel: props.photoLabel,
      destinationFor: () => props.destination,
      extraCheck: props.extraCheck,
    },
    onUploaded: props.onUploaded,
    reconcile: props.reconcile,
  });
  const { onBusyChange } = props;
  // Photos chosen while `askPhotoLabel` is on, waiting for their label.
  const [unlabelled, setUnlabelled] = useState<File[] | null>(null);
  useEffect(() => {
    onBusyChange?.(uploads.busy || unlabelled !== null);
  }, [uploads.busy, unlabelled, onBusyChange]);
  const ask = Boolean(props.askPhotoLabel) && !props.photoLabel;
  return (
    <div className={props.className}>
      <FileButton
        id={props.id}
        variant={props.variant}
        accept={props.accept ?? acceptFor(props.kinds)}
        multiple={props.multiple}
        disabled={props.disabled || (!props.multiple && uploads.busy)}
        aria-label={props["aria-label"]}
        onFiles={(chosen) => {
          const files = props.multiple ? chosen : chosen.slice(0, 1);
          // WHY by the slot's kinds, not the file's type: a phone photo (HEIC) may come with no
          // type at all, and only photo slots ask (videos and documents carry no label).
          if (ask && props.kinds.includes("image") && files.length > 0) setUnlabelled(files);
          else uploads.add(files);
        }}
      >
        {props.children}
      </FileButton>
      <UploadQueue uploads={uploads} className="mt-2" />
      <PhotoLabelDialog
        files={unlabelled}
        onCancel={() => setUnlabelled(null)}
        onConfirm={(label) => {
          if (unlabelled) uploads.add(unlabelled, label);
          setUnlabelled(null);
        }}
      />
    </div>
  );
}
