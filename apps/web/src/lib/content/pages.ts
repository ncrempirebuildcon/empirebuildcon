/**
 * Who may publish or change a page: shared by the page editor's buttons, its Settings tab and its
 * publishing panel. (The page's address on the website comes from the API as `path`.)
 *
 * SECURITY: these only decide what to show; the API checks the same rules on every call
 * (content/pages.py, content/page_blocks.py; ARCHITECTURE §11).
 */
import type { Schema } from "@/lib/api";

type PageRights = Pick<Schema<"Page">, "kind" | "publish_state" | "publish_at">;

/**
 * The permission that publishes this page: legal pages need `legal.publish` (D-017,
 * ARCHITECTURE §11), every other page `content.publish`.
 */
export function publishPermissionFor(page: Pick<Schema<"Page">, "kind">): string {
  return page.kind === "legal" ? "legal.publish" : "content.publish";
}

/**
 * True for a legal page that is live or scheduled to go live. Changing it at all needs
 * `legal.publish`.
 *
 * WHY scheduled counts (review H2): the schedule tick publishes the page's text at its time,
 * with nobody checking it again. If someone without `legal.publish` could edit a scheduled legal
 * page, wording no `legal.publish` holder approved would go live (D-017).
 */
export function isGuardedLegal(page: PageRights): boolean {
  return page.kind === "legal" && (page.publish_state === "published" || page.publish_at != null);
}

/** Whether this role may change the page (its fields and its blocks). */
export function canEditPage(page: PageRights, can: (permission: string) => boolean): boolean {
  return can("content.write") && (!isGuardedLegal(page) || can("legal.publish"));
}

/** Why the editor is read-only for this role, in words, or null when it isn't. */
export function readOnlyReason(page: PageRights, can: (permission: string) => boolean) {
  if (canEditPage(page, can)) return null;
  if (!can("content.write"))
    return "You can view this page. Editing needs the content.write permission.";
  return page.publish_state === "published"
    ? "This legal page is live: changing it needs the legal.publish permission."
    : "This legal page is scheduled to go live: changing it needs the legal.publish permission, so the text that goes live is the text an admin approved.";
}
