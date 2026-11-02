/**
 * Custom next/image loader for Cloudinary images (Phase 5 Task 5.2).
 *
 * Implements ARCHITECTURE §12 & D-033:
 *   - Injects `c_limit,f_auto,q_auto,w_<width>` transformations into Cloudinary delivery URLs.
 *   - Uses `c_limit` to prevent upscaling smaller originals beyond their native width (S12).
 *   - Replaces any existing delivery transformation without dropping public id folder paths.
 *   - Leaves non-Cloudinary URLs (fake media store, local assets, svgs) completely unmodified.
 */
import type { ImageLoaderProps } from "next/image";

const CLOUDINARY_HOST = "res.cloudinary.com";

function isTransformSegment(segment: string): boolean {
  if (!segment) return false;
  // A transformation segment consists of comma-separated parameter flags (e.g., c_limit,w_2560,f_auto).
  // Each parameter starts with 1-3 lowercase letters followed by an underscore.
  const parts = segment.split(",");
  return parts.length > 0 && parts.every((p) => /^[a-z]{1,3}_[^,]+$/.test(p));
}

export function cloudinaryLoader({ src, width, quality }: ImageLoaderProps): string {
  if (!src) return "";

  // Strict hostname check (S12)
  try {
    const parsed = new URL(src);
    if (parsed.hostname !== CLOUDINARY_HOST) {
      return src;
    }
  } catch {
    // Relative or invalid URLs are not modified
    return src;
  }

  const uploadMarker = "/image/upload/";
  const uploadIndex = src.indexOf(uploadMarker);
  if (uploadIndex === -1) {
    return src;
  }

  const prefix = src.slice(0, uploadIndex + uploadMarker.length);
  const rest = src.slice(uploadIndex + uploadMarker.length);

  // Split rest into path segments
  const segments = rest.split("/");
  const firstSegment = segments[0] ?? "";

  // Strip first segment ONLY if it is an existing transformation segment (S12)
  const hasExistingTransform = isTransformSegment(firstSegment);
  const pathAfterTransform = hasExistingTransform ? segments.slice(1).join("/") : rest;

  const q = quality ? `q_${quality}` : "q_auto";
  const transform = `c_limit,f_auto,${q},w_${width}`;

  return `${prefix}${transform}/${pathAfterTransform}`;
}

export default cloudinaryLoader;
