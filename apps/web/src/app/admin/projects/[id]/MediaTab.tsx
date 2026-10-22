"use client";
/**
 * Media tab (board NoirCmsProject, "Media manager"): one drop zone that sends each file to the
 * right list by type, and the project's Photos (gallery), Videos and Documents with counts.
 * Everything saves straight away; the project is re-read after each change so the cover, the
 * counts and the publish checklist stay current.
 *
 * Permissions: uploading, ordering, the cover, show/hide and removing need `media.upload`
 * (ARCHITECTURE §11), not `projects.write`; marketing staff manage media without editing the
 * project's facts. The API checks the permission on every call.
 *
 * COMPLIANCE: photos are labelled before they upload (PhotoLabelDialog), because the API keeps an
 * unlabelled photo hidden. The guidance under the lists (label every image honestly; hidden items
 * never appear; the first photo is the cover unless another is pinned) is the board's text.
 */
import { useState } from "react";
import { Button, FileDropZone, LiveRegion, SegmentedControl } from "@empire/ui";
import { DROP_ZONE_HINT, acceptFor, checkFile, type MediaKind } from "@/lib/media/files";
import type { AttachRole } from "@/lib/media/upload";
import { Panel } from "@/components/admin/states";
import { LinkedMediaList } from "@/components/admin/media/LinkedMediaList";
import { PhotoLabelDialog } from "@/components/admin/media/PhotoLabelDialog";
import { UploadQueue } from "@/components/admin/media/UploadQueue";
import { useUploads } from "@/components/admin/media/useUploads";
import { useReportDirty } from "./editorTypes";
import type { ProjectAdmin } from "./projectForm";

const ROLE_FOR: Record<MediaKind, AttachRole> = {
  image: "gallery",
  video: "video",
  document: "document",
};

const LIST_NAME: Record<MediaKind, string> = {
  image: "Photos",
  video: "Videos",
  document: "Documents",
};

export const MEDIA_DROP_ID = "media-drop";

export interface MediaTabProps {
  project: ProjectAdmin;
  /** False without `media.upload`: lists are read-only and there is no drop zone. */
  canUpload: boolean;
  onChanged: () => Promise<unknown>;
  reportDirty: (key: string, dirty: boolean) => void;
  onGoToTab: (tab: string) => void;
}

const plural = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`;

export function MediaTab({ project, canUpload, onChanged, reportDirty, onGoToTab }: MediaTabProps) {
  const [kind, setKind] = useState<MediaKind>("image");
  const photos = project.gallery ?? [];
  const videos = project.videos ?? [];
  const documents = project.documents ?? [];
  // Photos waiting for the honest-label question (PhotoLabelDialog) before they upload.
  const [pendingPhotos, setPendingPhotos] = useState<File[] | null>(null);
  const [notice, setNotice] = useState("");
  const uploads = useUploads({
    plan: {
      kinds: ["image", "video", "document"],
      targetFor: (k) => ({ ownerType: "project", ownerId: project.id, role: ROLE_FOR[k] }),
      destinationFor: (k) => LIST_NAME[k],
    },
    onUploaded: () => onChanged(),
    reconcile: onChanged,
  });
  // WHY: leaving the page cancels uploads in flight, so the leave warning covers them (and the
  // photos still waiting for their label).
  useReportDirty("media-uploads", uploads.busy || pendingPhotos !== null, reportDirty);

  function onFiles(files: File[]) {
    const checks = files.map((file) => ({ file, check: checkFile(file) }));
    // Show the list the first accepted file goes to, so the new item appears where staff look.
    const first = checks.find(({ check }) => check.ok)?.check;
    if (first?.ok) setKind(first.kind);
    // COMPLIANCE: photos wait for their honest label (asked once per batch); videos, documents
    // and refused files go to the queue at once.
    const photos = checks
      .filter(({ check }) => check.ok && check.kind === "image")
      .map(({ file }) => file);
    const others = files.filter((file) => !photos.includes(file));
    if (others.length > 0) uploads.add(others);
    if (photos.length > 0) setPendingPhotos(photos);
  }

  const shownPhotos = photos.filter((p) => p.is_visible).length;
  const summary = [
    `${plural(photos.length, "photo", "photos")} (${shownPhotos} shown)`,
    plural(videos.length, "video", "videos"),
    plural(documents.length, "document", "documents"),
  ].join(" · ");
  const common = {
    canEdit: canUpload,
    onChanged,
    ownerNoun: "project",
    focusAfterRemove: MEDIA_DROP_ID,
  };

  return (
    <Panel
      id="media"
      title="Media manager"
      description={summary}
      actions={
        <SegmentedControl
          label="Media type"
          value={kind}
          onChange={setKind}
          options={[
            { value: "image", label: `Photos · ${photos.length}` },
            { value: "video", label: `Videos · ${videos.length}` },
            { value: "document", label: `Documents · ${documents.length}` },
          ]}
        />
      }
    >
      {canUpload ? (
        <FileDropZone
          id={MEDIA_DROP_ID}
          onFiles={onFiles}
          accept={acceptFor(["image", "video", "document"])}
          hint={DROP_ZONE_HINT}
        />
      ) : (
        <p className="text-caption text-muted">
          You can see this project&apos;s media. Uploading and arranging it needs the media
          permission (admin, marketing or content editor).
        </p>
      )}
      <UploadQueue uploads={uploads} />
      <PhotoLabelDialog
        files={pendingPhotos}
        onCancel={() => {
          setPendingPhotos(null);
          setNotice("No photos were uploaded.");
        }}
        onConfirm={(label) => {
          if (pendingPhotos) uploads.add(pendingPhotos, label);
          setPendingPhotos(null);
          setNotice("");
        }}
      />
      <LiveRegion message={notice} />

      {kind === "image" ? (
        <LinkedMediaList
          {...common}
          idPrefix="media-photos"
          items={photos}
          layout="photos"
          label="Photos in display order"
          noun="photo"
          showCover
          emptyText="No photos yet. Upload the project's photos and renders above."
        />
      ) : kind === "video" ? (
        <LinkedMediaList
          {...common}
          idPrefix="media-videos"
          items={videos}
          layout="videos"
          label="Videos in display order"
          noun="video"
          emptyText="No videos yet."
        />
      ) : (
        <>
          <LinkedMediaList
            {...common}
            idPrefix="media-documents"
            items={documents}
            layout="documents"
            label="Documents in display order"
            noun="document"
            emptyText="No documents yet."
          />
          <p className="flex flex-wrap items-center gap-x-2 text-caption text-muted">
            RERA certificate, approved plans and the RERA QR code are kept under Documents.
            <Button variant="tertiary" className="min-h-11" onClick={() => onGoToTab("documents")}>
              Go to Documents
            </Button>
          </p>
        </>
      )}

      <p className="border-t border-line pt-3 text-caption text-muted">
        Drag, or use Move up and Move down, to set the order. The first photo is the cover unless
        you pin another with the star. Hidden items stay in the CMS but never appear on the website.
        Label every image honestly: artist&apos;s impression, actual photo, or progress photo with
        its month.
      </p>
    </Panel>
  );
}
