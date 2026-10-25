"use client";
/**
 * The post editor's publishing panel: what the website shows now, the API's blockers, and
 * Archive / Restore / Delete draft (only drafts never published can be deleted; ARCHITECTURE §6).
 * SECURITY: taking a live post down needs `content.publish`; the API checks every call again.
 */
import { Button } from "@empire/ui";
import type { usePublishActions } from "@/components/admin/content/usePublishActions";
import type { Post } from "./postForm";

export function PostPublishing({
  post,
  actions,
  dirty,
  canWrite,
  canPublish,
}: {
  post: Post;
  actions: ReturnType<typeof usePublishActions<Post>>;
  dirty: boolean;
  canWrite: boolean;
  canPublish: boolean;
}) {
  const state = post.publish_state;
  const card =
    "flex min-w-0 flex-[1_1_280px] flex-col gap-2.5 rounded-card border bg-noir-800 p-4.5";
  const deletable = state === "draft" && !post.published_at;
  return (
    <aside aria-label="Publishing" className="flex flex-wrap items-start gap-4">
      <section
        id="post-publish-status"
        aria-labelledby="post-publish-title"
        className={`${card} border-gold-line-strong`}
      >
        <h2 id="post-publish-title" className="text-base font-bold">
          {state === "published"
            ? "Published"
            : state === "archived"
              ? "Archived"
              : "Before you can publish"}
        </h2>
        {state === "published" ? (
          <p className="text-caption">
            On the website at {post.path}. Saved changes show straight away.
          </p>
        ) : state === "archived" ? (
          <p className="text-caption">
            Hidden from the website. Restore it as a draft to work on it again.
          </p>
        ) : post.publish_blockers.length === 0 ? (
          <p className="text-small font-semibold text-ivory">Nothing is blocking publishing.</p>
        ) : (
          <ul
            className="flex list-disc flex-col gap-1 pl-5 text-small"
            aria-label="What is missing"
          >
            {post.publish_blockers.map((blocker) => (
              <li key={blocker}>{blocker}</li>
            ))}
          </ul>
        )}
        {state === "draft" && dirty ? (
          <p className="text-caption font-semibold text-danger">
            Save your changes before publishing.
          </p>
        ) : null}
        {!canPublish ? (
          <p className="text-caption text-muted">
            Publishing needs the content.publish permission.
          </p>
        ) : null}
      </section>
      {canWrite && (state !== "published" || canPublish) ? (
        <section aria-labelledby="post-archive-title" className={`${card} border-line`}>
          <h2 id="post-archive-title" className="text-base font-bold">
            {state === "archived" ? "Archived" : deletable ? "Archive or delete" : "Archive"}
          </h2>
          {state === "archived" ? (
            <Button
              variant="secondary"
              className="self-start"
              loading={actions.busy === "restore"}
              onClick={actions.restore}
            >
              Restore as draft
            </Button>
          ) : (
            <div className="flex flex-wrap gap-2">
              <Button variant="danger" onClick={actions.askArchive}>
                Archive post
              </Button>
              {deletable ? (
                <Button variant="danger" onClick={actions.askDelete}>
                  Delete draft
                </Button>
              ) : null}
            </div>
          )}
          {!deletable && state !== "archived" ? (
            <p className="text-caption text-muted">
              Posts that were ever published are archived, not deleted.
            </p>
          ) : null}
        </section>
      ) : null}
    </aside>
  );
}
