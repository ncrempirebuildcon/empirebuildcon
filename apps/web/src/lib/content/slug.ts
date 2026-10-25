/**
 * Web addresses (slugs) for pages and posts: lower-case letters, digits and single hyphens, as
 * the API requires (`^[a-z0-9]+(?:-[a-z0-9]+)*$`). Slugs stay English for every language (D-014).
 */

export const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

/** A slug suggested from a title: "Home loan: documents checklist" → "home-loan-documents-checklist". */
export function slugify(title: string): string {
  return title
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 120)
    .replace(/-+$/g, "");
}

/** The problem with a typed slug, or null. */
export function slugProblem(slug: string): string | null {
  if (slug === "") return "Enter a web address.";
  if (slug.length > 120) return "Keep the web address to 120 characters or fewer.";
  if (!SLUG_RE.test(slug)) {
    return "Use lower-case letters, numbers and single hyphens only, e.g. home-loan-guide.";
  }
  return null;
}
