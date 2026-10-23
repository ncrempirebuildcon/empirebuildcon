"use client";
/**
 * The SEO tab's share image (board NoirCmsProject, "Share image (1200 × 630)"): the picture shown
 * when the project page is shared on WhatsApp or social media. Pick one of the project's photos,
 * or upload a new image, then "Save draft" saves the choice (`seo.og_image_id`), like the rest of
 * the SEO fields.
 *
 * How it works:
 *   1. The choices are the project's photos (gallery) as a radio group of thumbnails, plus
 *      "Use no share image".
 *   2. "Upload a share image" sends a photo through the API into the library (not attached to a
 *      list, so it doesn't appear among the project's photos) and selects it.
 *      WHY not the `og_image` link role: the project's share image is `seo.og_image_id` (API
 *      contract notes, part 2); the library refuses to delete a file a project uses as its share
 *      image (409), so the choice can't be left pointing at a missing file.
 *   3. The preview shows the chosen photo, the saved share image (`project.og_image`), or the
 *      image just uploaded.
 */
import { useState } from "react";
import { Button, cx } from "@empire/ui";
import type { Media } from "@/lib/media/upload";
import { MediaThumb } from "@/components/admin/media/MediaThumb";
import { SlotUploader } from "@/components/admin/media/SlotUploader";
import type { ProjectAdmin } from "./projectForm";

export interface ShareImagePickerProps {
  project: ProjectAdmin;
  /** The chosen image's id ("" for none), from the form. */
  value: string;
  onChange: (id: string) => void;
  /** False without `projects.write` (choosing is a project field). */
  canWrite: boolean;
  /** False without `media.upload`. */
  canUpload: boolean;
  reportDirty: (key: string, dirty: boolean) => void;
  error?: string;
}

export function ShareImagePicker({
  project,
  value,
  onChange,
  canWrite,
  canUpload,
  reportDirty,
  error,
}: ShareImagePickerProps) {
  const [uploaded, setUploaded] = useState<Media | null>(null);
  const photos = project.gallery ?? [];
  const known: Media[] = [
    ...photos,
    ...(project.og_image ? [project.og_image] : []),
    ...(uploaded ? [uploaded] : []),
  ];
  const chosen = value ? (known.find((m) => m.id === value) ?? null) : null;
  const groupName = `share-image-${project.id}`;

  return (
    <div className="flex flex-col gap-3">
      <span id="share-image-label" className="text-small font-semibold text-ivory">
        Share image (1200 × 630)
      </span>
      {chosen ? (
        <MediaThumb
          media={chosen}
          className="aspect-[1200/630] w-full rounded-tile border border-line-strong"
        />
      ) : (
        <div className="flex aspect-[1200/630] w-full items-center justify-center rounded-tile border border-dashed border-line-strong bg-noir-700 px-4 text-center text-caption text-muted">
          {value ? "The chosen image can't be previewed here." : "No share image chosen."}
        </div>
      )}
      {error ? <p className="text-caption text-danger">{error}</p> : null}

      <fieldset disabled={!canWrite} className="flex min-w-0 flex-col gap-2">
        <legend className="mb-1 text-caption font-semibold text-ivory">
          Choose from this project&apos;s photos
        </legend>
        {photos.length === 0 ? (
          <p className="text-caption text-muted">
            No photos yet. Upload some in the Media tab, or upload a share image below.
          </p>
        ) : (
          <ul className="grid grid-cols-[repeat(auto-fill,minmax(88px,1fr))] gap-2">
            {photos.map((photo) => (
              <li key={photo.link_id}>
                <label
                  className={cx(
                    "relative block cursor-pointer overflow-hidden rounded-tag border-2",
                    value === photo.id ? "border-gold-400" : "border-transparent",
                  )}
                >
                  <input
                    type="radio"
                    name={groupName}
                    value={photo.id}
                    checked={value === photo.id}
                    onChange={() => onChange(photo.id)}
                    className="peer sr-only"
                  />
                  {/* The thumbnail's alt text (alt text, else title) names the choice. */}
                  <MediaThumb media={photo} dim={!photo.is_visible} />
                  <span
                    aria-hidden="true"
                    className="pointer-events-none absolute inset-0 rounded-tag peer-focus-visible:outline-2 peer-focus-visible:outline-offset-[-2px] peer-focus-visible:outline-gold-300"
                  />
                </label>
              </li>
            ))}
          </ul>
        )}
        {value ? (
          <Button variant="tertiary" className="min-h-11 self-start" onClick={() => onChange("")}>
            Use no share image
          </Button>
        ) : null}
      </fieldset>

      {canUpload && canWrite ? (
        <SlotUploader
          id="share-image-upload"
          variant="secondary"
          target={null}
          kinds={["image"]}
          destination="the library; save the draft to use it as the share image"
          onUploaded={(media) => {
            setUploaded(media);
            onChange(media.id);
          }}
          onBusyChange={(busy) => reportDirty("share-image-upload", busy)}
        >
          Upload a share image
        </SlotUploader>
      ) : null}
      <p className="text-caption text-muted">
        Best at 1200 × 630 pixels. It is used when the page is shared; it is saved with Save draft.
      </p>
    </div>
  );
}
