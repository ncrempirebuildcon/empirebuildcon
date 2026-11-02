/**
 * Public image component for the Empire website (Phase 5 Task 5.2).
 *
 * Implements ARCHITECTURE §12 & D-033:
 *   - Custom Cloudinary loader for responsive widths and automatic format/quality.
 *   - Preserves fake media store and local image paths.
 *   - Alt text is required (never empty without explicit decorative role).
 *   - Displays honest labels (Artist's impression, Actual photo, Progress photo) and
 *     the SAMPLE badge when specified.
 */
import Image, { type ImageProps } from "next/image";
import cloudinaryLoader from "@/lib/cloudinary-loader";

export type ImageLabelKind =
  "artist_impression" | "actual_photo" | "sample_flat" | "progress_photo" | string;

export interface PublicImageProps extends Omit<ImageProps, "alt"> {
  alt: string;
  label?: ImageLabelKind | null;
  labelMonth?: string | null;
  isSample?: boolean;
  showBadge?: boolean;
  containerClassName?: string;
}

const LABEL_TEXTS: Record<string, string> = {
  artist_impression: "Artist's impression",
  actual_photo: "Actual photo",
  sample_flat: "Sample flat",
  progress_photo: "Progress photo",
};

export function getHonestLabelText(
  label?: string | null,
  labelMonth?: string | null,
): string | null {
  if (!label) return null;
  const base = LABEL_TEXTS[label] || label.replace(/_/g, " ");
  if (label === "progress_photo" && labelMonth) {
    return `${base} · ${labelMonth}`;
  }
  return base;
}

export function PublicImage({
  src,
  alt,
  label,
  labelMonth,
  isSample = false,
  showBadge = true,
  className = "",
  containerClassName = "",
  sizes = "(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw",
  ...props
}: PublicImageProps) {
  const labelText = showBadge ? getHonestLabelText(label, labelMonth) : null;
  const hasBadges = Boolean(labelText || isSample);

  const img = (
    <Image
      loader={cloudinaryLoader}
      src={src}
      alt={alt}
      sizes={sizes}
      className={className}
      {...props}
    />
  );

  if (!hasBadges && !containerClassName) {
    return img;
  }

  return (
    <div className={`relative inline-block overflow-hidden ${containerClassName}`}>
      {img}
      {labelText && (
        <span
          className="absolute bottom-2.5 left-2.5 rounded-md bg-noir-900/85 px-2.5 py-1 text-xs text-sand-200 backdrop-blur-xs"
          data-testid="honest-label"
        >
          {labelText}
        </span>
      )}
      {isSample && (
        <span
          className="absolute top-2.5 right-2.5 rounded-full border border-danger/60 bg-noir-900/85 px-2 py-0.5 text-[11px] font-bold text-danger backdrop-blur-xs"
          data-testid="sample-badge"
        >
          SAMPLE
        </span>
      )}
    </div>
  );
}

export default PublicImage;
