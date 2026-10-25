"use client";
/**
 * The page's publishing panel: what the website shows now, the schedule, the API's
 * `publish_blockers`, and Archive / Restore / Delete (spec Phase 4 part 4 §3).
 *
 * SECURITY: buttons show only with the matching permission (usePageActions.tsx explains which);
 * the API checks every call again.
 */
import { Button } from "@empire/ui";
import { formatDateTime } from "@/lib/dates";
import { canBeDeleted, type PageActions } from "./usePageActions";
import type { Page } from "./pageForm";

export interface PagePublishPanelProps {
  page: Page;
  actions: PageActions;
  dirty: boolean;
  canWrite: boolean;
  /** `content.publish`, or `legal.publish` for a legal page. */
  canPublish: boolean;
}

export function PagePublishPanel({
  page,
  actions,
  dirty,
  canWrite,
  canPublish,
}: PagePublishPanelProps) {
  const state = page.publish_state;
  const card =
    "flex min-w-0 flex-[1_1_280px] flex-col gap-2.5 rounded-card border bg-noir-800 p-4.5";
  // Archiving a live page takes it off the website: a publishing decision (usePageActions.tsx).
  // Pages that come with the website (`is_required`) are never archived or deleted (L8).
  const canArchive = canWrite && !page.is_required && (state !== "published" || canPublish);
  const schedule = [
    page.publish_at ? `Publishes on ${formatDateTime(page.publish_at)}` : null,
    page.unpublish_at ? `Taken down on ${formatDateTime(page.unpublish_at)}` : null,
  ].filter(Boolean);

  return (
    <aside aria-label="Publishing" className="flex flex-wrap items-start gap-4">
      <section
        id="page-publish-status"
        aria-labelledby="page-publish-title"
        className={`${card} border-gold-line-strong`}
      >
        <h2 id="page-publish-title" className="text-base font-bold">
          {state === "published"
            ? "Published"
            : state === "archived"
              ? "Archived"
              : "Before you can publish"}
        </h2>
        {state === "published" ? (
          <p className="text-caption">
            On the website at {page.path}. Saved changes show on the website straight away.
          </p>
        ) : state === "archived" ? (
          <p className="text-caption">
            Hidden from the website. Restore it as a draft to work on it again.
          </p>
        ) : page.publish_blockers.length === 0 ? (
          <p className="text-small font-semibold text-ivory">Nothing is blocking publishing.</p>
        ) : (
          <ul
            className="flex list-disc flex-col gap-1 pl-5 text-small"
            aria-label="What is missing"
          >
            {page.publish_blockers.map((blocker) => (
              <li key={blocker}>{blocker}</li>
            ))}
          </ul>
        )}
        {schedule.length > 0 ? (
          <p className="text-caption">{schedule.join(" · ")} (India time).</p>
        ) : null}
        {state === "draft" && dirty ? (
          <p className="text-caption font-semibold text-danger">
            Save your changes before publishing.
          </p>
        ) : null}
        {!canPublish ? (
          <p className="text-caption text-muted">
            {page.kind === "legal"
              ? "Publishing a legal page needs the legal.publish permission."
              : "Publishing needs the content.publish permission."}
          </p>
        ) : null}
      </section>

      {canArchive ? (
        <section aria-labelledby="page-archive-title" className={`${card} border-line`}>
          <h2 id="page-archive-title" className="text-base font-bold">
            Archive
          </h2>
          {state === "archived" ? (
            <>
              <p className="text-caption">
                This page is archived. Its blocks and history stay in the CMS.
              </p>
              <Button
                variant="secondary"
                className="self-start"
                loading={actions.busy === "restore"}
                onClick={actions.restore}
              >
                Restore as draft
              </Button>
            </>
          ) : (
            <>
              <p className="text-caption">
                Pages that were ever published are archived, not deleted. Archiving removes the page
                from the website and the menu.
              </p>
              <Button variant="danger" className="self-start" onClick={actions.askArchive}>
                Archive page
              </Button>
            </>
          )}
        </section>
      ) : null}

      {canWrite && !page.is_required && (page.kind !== "legal" || canPublish) ? (
        <section aria-labelledby="page-delete-title" className={`${card} border-line`}>
          <h2 id="page-delete-title" className="text-base font-bold">
            Delete
          </h2>
          {canBeDeleted(page) ? (
            <Button variant="danger" className="self-start" onClick={actions.askDelete}>
              Delete draft
            </Button>
          ) : (
            <p className="text-caption text-muted">
              Only drafts that were never published can be deleted. Archive it instead.
            </p>
          )}
        </section>
      ) : null}
    </aside>
  );
}
