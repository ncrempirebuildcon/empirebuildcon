"use client";
/**
 * The Floor plan cell of the configurations table (board NoirCmsProject, "Configurations"): the
 * plan's thumbnail on an ivory tile, and Add/Replace and Remove. One plan per configuration, an
 * image or a PDF; uploading a new one replaces the old link in the same step (the old file stays
 * in the library).
 *
 * DESIGN_SYSTEM §7: floor plans always sit on an ivory tile so they stay readable. Image plans
 * are line drawings, so they upload lossless (WebP or PNG; resize.ts "plan").
 */
import { useEffect, useState } from "react";
import { LiveRegion } from "@empire/ui";
import { isImage, isPdf } from "@/lib/media/files";
import { DetachButton } from "@/components/admin/media/DetachButton";
import { MediaThumb } from "@/components/admin/media/MediaThumb";
import { SlotUploader } from "@/components/admin/media/SlotUploader";
import type { Configuration } from "./editorTypes";

export function FloorPlanCell({
  configuration,
  canUpload,
  onChanged,
  reportDirty,
}: {
  configuration: Configuration;
  canUpload: boolean;
  onChanged: () => Promise<unknown>;
  reportDirty: (key: string, dirty: boolean) => void;
}) {
  const [message, setMessage] = useState("");
  const plan = configuration.floor_plans?.[0] ?? null;
  const uploadId = `floor-plan-upload-${configuration.id}`;
  const dirtyKey = `floor-plan-${configuration.id}`;
  // A removed configuration takes its uploader with it; clear its "upload running" flag too.
  useEffect(() => () => reportDirty(dirtyKey, false), [dirtyKey, reportDirty]);
  return (
    <div className="flex flex-wrap items-center gap-2">
      {plan ? (
        <a
          href={plan.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block w-14 shrink-0 rounded-tag"
        >
          <MediaThumb media={plan} ivory className="rounded-tag" />
          <span className="sr-only">{` Open the floor plan of ${configuration.name} (opens in a new tab)`}</span>
        </a>
      ) : (
        <span className="text-xs text-muted">No plan yet</span>
      )}
      {canUpload ? (
        <>
          <SlotUploader
            id={uploadId}
            variant="tertiary"
            className="[&>button]:min-h-11"
            target={{ ownerType: "configuration", ownerId: configuration.id, role: "floor_plan" }}
            kinds={["image", "document"]}
            accept="image/jpeg,image/png,image/webp,image/avif,application/pdf,.jpg,.jpeg,.png,.webp,.avif,.pdf"
            extraCheck={(file) =>
              isImage(file) || isPdf(file)
                ? null
                : `${file.name}: a floor plan is a photo or scan (JPG, PNG, WebP, AVIF) or a PDF.`
            }
            destination={`the floor plan of ${configuration.name}`}
            aria-label={`${plan ? "Replace" : "Add"} floor plan for ${configuration.name}`}
            encoding="plan"
            onUploaded={() => onChanged()}
            reconcile={onChanged}
            onBusyChange={(busy) => reportDirty(dirtyKey, busy)}
          >
            {plan ? "Replace" : "Add floor plan"}
          </SlotUploader>
          {plan ? (
            <DetachButton
              linkId={plan.link_id}
              title={`the floor plan of ${configuration.name}`}
              ownerNoun="configuration"
              onChanged={onChanged}
              focusAfter={uploadId}
              onDone={setMessage}
            />
          ) : null}
        </>
      ) : null}
      <LiveRegion message={message} />
    </div>
  );
}
