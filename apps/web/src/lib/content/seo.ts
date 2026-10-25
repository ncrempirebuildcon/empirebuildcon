/**
 * The SEO fields of pages and posts as the form edits them, and back to the API's `Seo` object
 * (title ≤ 70, description ≤ 170, share image, noindex, canonical path).
 *
 * WHY the share image as a Media object in the form: the field shows its thumbnail; only its id
 * is sent (`og_image_id`).
 */
import type { Schema } from "@/lib/api";
import type { Media } from "@/lib/media/upload";

export type Seo = Schema<"Seo">;

export interface SeoForm {
  title: string;
  description: string;
  canonical_path: string;
  noindex: boolean;
  /** The share image's id ("" for none) and, when known, its details for the preview. */
  og_image_id: string;
  og_image: Media | null;
}

export function toSeoForm(
  seo: Seo | null | undefined,
  media: (id: string) => Media | null,
): SeoForm {
  const id = seo?.og_image_id ?? "";
  return {
    title: seo?.title ?? "",
    description: seo?.description ?? "",
    canonical_path: seo?.canonical_path ?? "",
    noindex: seo?.noindex ?? false,
    og_image_id: id,
    og_image: id ? media(id) : null,
  };
}

const orNull = (value: string) => (value.trim() === "" ? null : value.trim());

export function toSeo(form: SeoForm): Seo {
  return {
    title: orNull(form.title),
    description: orNull(form.description),
    canonical_path: orNull(form.canonical_path),
    noindex: form.noindex,
    og_image_id: form.og_image_id || null,
  };
}

/** True when two forms would save the same `Seo`. */
export const sameSeo = (a: SeoForm, b: SeoForm) =>
  JSON.stringify(toSeo(a)) === JSON.stringify(toSeo(b));
