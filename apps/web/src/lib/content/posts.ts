/**
 * Blog post helpers: suggested categories (board NoirCmsContent's category list; staff may type
 * another) and tags typed as one comma-separated line.
 */

/** Suggested categories, from the design board. A post may use any other words too. */
export const POST_CATEGORIES: readonly string[] = [
  "Buying guide",
  "RERA & legal",
  "Construction updates",
  "NRI",
  "News",
];

/** The most tags a post takes, and their length (the API's limits). */
export const MAX_TAGS = 10;
export const MAX_TAG_LENGTH = 40;

/** "home loan, NRI , ,documents" → ["home loan", "NRI", "documents"]. */
export function parseTags(line: string): string[] {
  return line
    .split(",")
    .map((tag) => tag.trim().replace(/\s+/g, " "))
    .filter(Boolean);
}

/** The problem with typed tags, or null. */
export function tagsProblem(tags: readonly string[]): string | null {
  if (tags.length > MAX_TAGS) return `Use at most ${MAX_TAGS} tags.`;
  const long = tags.find((tag) => tag.length > MAX_TAG_LENGTH);
  if (long)
    return `Keep each tag to ${MAX_TAG_LENGTH} characters (“${long.slice(0, 20)}…” is longer).`;
  const seen = new Set<string>();
  for (const tag of tags) {
    if (seen.has(tag.toLowerCase())) return `“${tag}” appears twice.`;
    seen.add(tag.toLowerCase());
  }
  return null;
}
