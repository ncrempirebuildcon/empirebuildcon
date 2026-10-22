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
 */
import { useEffect } from "react";
import { FileButton, type ButtonVariant } from "@empire/ui";
import { acceptFor, type MediaKind } from "@/lib/media/files";
import type { ImageEncoding } from "@/lib/media/resize";
import type { AttachTarget, Media } from "@/lib/media/upload";
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
  useEffect(() => {
    onBusyChange?.(uploads.busy);
  }, [uploads.busy, onBusyChange]);
  return (
    <div className={props.className}>
      <FileButton
        id={props.id}
        variant={props.variant}
        accept={props.accept ?? acceptFor(props.kinds)}
        multiple={props.multiple}
        disabled={props.disabled || (!props.multiple && uploads.busy)}
        aria-label={props["aria-label"]}
        onFiles={(files) => uploads.add(props.multiple ? files : files.slice(0, 1))}
      >
        {props.children}
      </FileButton>
      <UploadQueue uploads={uploads} className="mt-2" />
    </div>
  );
}
