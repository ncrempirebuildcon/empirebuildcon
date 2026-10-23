"use client";
/**
 * Progress photos of one construction update (board NoirCmsProject, "Progress": the photo strip
 * with "+ Add photo"). Photos upload straight to the update (role `gallery`, shown on the website
 * as the update's photos) and are listed with the same controls as the project's photos, without
 * the cover star.
 *
 * WHY the label is set for the user here: a photo added to a dated construction update is a
 * progress photo of that update's month by definition, so it is uploaded labelled "Progress
 * photo" with the update's month. Staff can still change both in Edit details.
 */
import { useEffect } from "react";
import { formatCalendarDate } from "@/lib/dates";
import { monthOf } from "@/lib/media/labels";
import { LinkedMediaList } from "@/components/admin/media/LinkedMediaList";
import { SlotUploader } from "@/components/admin/media/SlotUploader";
import type { ConstructionUpdate } from "./editorTypes";

export function ProgressPhotos({
  update,
  canUpload,
  onChanged,
  reportDirty,
}: {
  update: ConstructionUpdate;
  canUpload: boolean;
  onChanged: () => Promise<unknown>;
  reportDirty: (key: string, dirty: boolean) => void;
}) {
  const photos = update.photos ?? [];
  const date = formatCalendarDate(update.update_date);
  const uploadId = `progress-photos-upload-${update.id}`;
  const dirtyKey = `progress-photos-${update.id}`;
  useEffect(() => () => reportDirty(dirtyKey, false), [dirtyKey, reportDirty]);

  return (
    <section aria-label={`Photos of the ${date} update`} className="flex flex-col gap-2">
      {/* WHY always rendered, even empty: its live region and dialogs must outlive the last
          photo being removed, so the removal is still announced. */}
      <LinkedMediaList
        idPrefix={`progress-${update.id}`}
        items={photos}
        layout="photos"
        label={`Photos of the ${date} update, in display order`}
        noun="photo"
        ownerNoun="update"
        canEdit={canUpload}
        onChanged={onChanged}
        focusAfterRemove={uploadId}
        emptyText="No progress photos for this update yet."
      />
      {canUpload ? (
        <SlotUploader
          id={uploadId}
          variant="secondary"
          className="self-start"
          target={{ ownerType: "construction_update", ownerId: update.id, role: "gallery" }}
          kinds={["image"]}
          multiple
          destination={`the ${date} update`}
          aria-label={`+ Add photos to the ${date} update`}
          photoLabel={{ label: "progress_photo", labelMonth: monthOf(update.update_date) }}
          onUploaded={() => onChanged()}
          reconcile={onChanged}
          onBusyChange={(busy) => reportDirty(dirtyKey, busy)}
        >
          + Add photos
        </SlotUploader>
      ) : null}
    </section>
  );
}
