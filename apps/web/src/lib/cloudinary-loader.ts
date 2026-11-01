/**
 * Custom next/image loader for Cloudinary images (Phase 5 Task 5.2).
 *
 * Implements ARCHITECTURE §12 & D-033:
 *   - Injects `f_auto,q_auto,w_<width>` transformations into Cloudinary image delivery URLs.
 *   - Replaces any existing delivery transformation with the requested width step.
 *   - Leaves non-Cloudinary URLs (fake media store, local assets, svgs) completely unmodified.
 */
import type { ImageLoaderProps } from "next/image";

const CLOUDINARY_HOST = "res.cloudinary.com";

export function cloudinaryLoader({ src, width, quality }: ImageLoaderProps): string {
  if (!src) return "";

  // Only transform Cloudinary URLs
  if (!src.includes(CLOUDINARY_HOST)) {
    return src;
  }

  const uploadMarker = "/image/upload/";
  const uploadIndex = src.indexOf(uploadMarker);
  if (uploadIndex === -1) {
    return src;
  }

  const prefix = src.slice(0, uploadIndex + uploadMarker.length);
  const rest = src.slice(uploadIndex + uploadMarker.length);

  // Split into segments
  const segments = rest.split("/");
  const firstSegment = segments[0] ?? "";
  // If the first segment is an existing transformation (does not start with 'v' followed by digits)
  // and there are further segments, remove it.
  const hasExistingTransform = segments.length > 1 && !/^v\d+$/.test(firstSegment);
  const pathAfterTransform = hasExistingTransform ? segments.slice(1).join("/") : rest;

  const q = quality ? `q_${quality}` : "q_auto";
  const transform = `f_auto,${q},w_${width}`;

  return `${prefix}${transform}/${pathAfterTransform}`;
}

export default cloudinaryLoader;
