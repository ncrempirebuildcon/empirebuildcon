"use client";
/**
 * The banner on every legal page's editor (spec Phase 4 part 4 §2).
 *
 * COMPLIANCE (D-017): legal texts are Claude's drafts until the owner approves them. The banner
 * says DRAFT in words (not only colour) while the text carries the draft mark, and names the
 * permission that publishes legal pages (`legal.publish`).
 */
import type { Page } from "./pageForm";

export function LegalBanner({ page, canPublish }: { page: Page; canPublish: boolean }) {
  return (
    <div
      role="note"
      aria-label="Legal page"
      className="flex flex-col gap-1.5 rounded-tile border border-danger bg-noir-700 px-4 py-3 text-small"
    >
      {page.is_draft_text ? (
        <p>
          <strong className="text-danger">DRAFT</strong> · This legal text is a placeholder: Claude
          drafts it and the owner approves it (D-017). The live site refuses to publish it while it
          is marked DRAFT.
        </p>
      ) : (
        <p>
          <strong className="text-ivory">Legal page</strong> · The text has no DRAFT mark. Check
          that the owner approved this wording before publishing.
        </p>
      )}
      <p className="text-caption text-muted">
        Publishing or unpublishing a legal page needs the legal.publish permission
        {canPublish ? " (your role has it)." : ", which your role doesn't have. Ask an admin."}
      </p>
    </div>
  );
}
