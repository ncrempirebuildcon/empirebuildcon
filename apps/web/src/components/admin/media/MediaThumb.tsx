"use client";
/**
 * A preview of one media item in the CMS: the photo, a video's poster (or a play tile), or a
 * document tile showing its format.
 *
 * Accessibility: every image has alt text, the item's own alt text or else its title (spec
 * Phase 4 part 2 §3). Icons are decorative; the format is written out.
 *
 * WHY a plain <img> and not next/image: the CMS shows files from the store's own thumbnail URLs
 * (Cloudinary transformations, or the fake store in development). The public site's image loader
 * arrives in Phase 5 (TODO(phase-5)); routing CMS previews through /_next/image would only add a
 * second resize.
 *
 * QR codes and floor plans sit on an `ivory-tile` (DESIGN_SYSTEM §7) so they stay readable.
 */
import { cx } from "@empire/ui";
import type { Media } from "@/lib/media/upload";

export type ThumbShape = "photo" | "video" | "square";

const SHAPE: Record<ThumbShape, string> = {
  photo: "aspect-[4/3]",
  video: "aspect-video",
  square: "aspect-square",
};

/** The alt text for an item: its own alt text, else its title. */
export const altFor = (media: Pick<Media, "alt_text" | "title">) =>
  media.alt_text?.trim() || media.title;

export function MediaThumb({
  media,
  shape = "photo",
  ivory = false,
  dim = false,
  className,
}: {
  media: Media;
  shape?: ThumbShape;
  /** Draw on an ivory tile and contain the image (QR codes, floor plans). */
  ivory?: boolean;
  /** Dimmed, for items hidden from the website. */
  dim?: boolean;
  className?: string;
}) {
  const frame = cx(
    "relative block overflow-hidden",
    SHAPE[shape],
    ivory ? "bg-ivory-tile p-1" : "bg-noir-700",
    dim && "opacity-40",
    className,
  );
  const src = media.thumbnail_url ?? (media.kind === "image" ? media.url : null);
  if (src) {
    return (
      <span className={frame}>
        {/* eslint-disable-next-line @next/next/no-img-element -- WHY: see the file header. */}
        <img
          src={src}
          alt={altFor(media)}
          loading="lazy"
          decoding="async"
          className={cx("block size-full", ivory ? "object-contain" : "object-cover")}
        />
        {media.kind === "video" ? <PlayMark /> : null}
      </span>
    );
  }
  return (
    <span className={cx(frame, "flex flex-col items-center justify-center gap-1")}>
      {media.kind === "video" ? <PlayMark inline /> : <DocumentIcon />}
      <span
        className={cx(
          "text-xs font-extrabold tracking-[0.08em]",
          ivory ? "text-ink" : "text-gold-300",
        )}
      >
        {media.format.toUpperCase()}
      </span>
    </span>
  );
}

function PlayMark({ inline = false }: { inline?: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={cx(
        "flex size-13 items-center justify-center rounded-pill bg-gold-500",
        !inline && "absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2",
      )}
    >
      <svg width="22" height="22" viewBox="0 0 24 24" className="fill-noir-900">
        <path d="M8 5v14l11-7z" />
      </svg>
    </span>
  );
}

export function DocumentIcon({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      width="26"
      height="26"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      className={cx("shrink-0 text-gold-400", className)}
    >
      <path d="M14 3H6v18h12V7z" />
      <path d="M14 3v4h4M9 13h6M9 17h6" />
    </svg>
  );
}
