"use client";
/**
 * Publishing actions and the side panel (board NoirCmsProject, "Publishing" aside): the
 * "Before you can publish" checklist from the API's `publish_blockers`, Publish/Unpublish,
 * Archive (with the board's text), Duplicate, and Delete for drafts that were never published.
 *
 * SECURITY: buttons show only with the matching permission (projects.publish, projects.write,
 * projects.delete), but the API checks every call again (ARCHITECTURE §11).
 * COMPLIANCE: Publish stays locked while the API lists blockers (RERA number and QR, D-002;
 * sample data in production, D-015). The panel only shows them; the API enforces them.
 */
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button, ConfirmDialog } from "@empire/ui";
import { api, call } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { problemMessage, toProblem } from "@/lib/problems";
import { PROJECTS_PATH, projectPath } from "@/lib/routes";
import type { ProjectAdmin } from "./projectForm";

type Action = "publish" | "unpublish" | "archive" | "restore" | "duplicate" | "delete";
type Confirmable = "unpublish" | "archive" | "delete";

export interface ProjectActionsOptions {
  project: ProjectAdmin;
  /** Called with the project the API returned after an action. */
  onUpdated: (project: ProjectAdmin) => void;
  /** Re-reads the project (e.g. after a refused publish, to show the latest blockers). */
  refresh: () => Promise<unknown>;
  /** A sentence for the editor's status line ("Published."). */
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}

/** True when the API would allow Delete: a draft that was never published. */
export function canBeDeleted(project: ProjectAdmin): boolean {
  return project.publish_state === "draft" && !project.published_at;
}

export function useProjectActions(options: ProjectActionsOptions) {
  const { project } = options;
  const router = useRouter();
  const [busy, setBusy] = useState<Action | null>(null);
  const [confirm, setConfirm] = useState<Confirmable | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const id = project.id;
  const path = { params: { path: { id } } };

  async function run(action: Action, work: () => Promise<void>) {
    if (busy) return;
    setBusy(action);
    setDialogError(null);
    try {
      await work();
      setConfirm(null);
    } catch (err) {
      const message = problemMessage(err, "That didn't work. Please try again.");
      if (confirm) setDialogError(message);
      else options.onError(message);
    } finally {
      setBusy(null);
    }
  }

  const publish = () =>
    run("publish", async () => {
      try {
        options.onUpdated(await call(api.POST("/api/v1/admin/projects/{id}/publish", path)));
        options.onNotice("Published. The project is live.");
      } catch (err) {
        if (toProblem(err).status === 409) await options.refresh().catch(() => undefined);
        throw err;
      }
    });

  const unpublish = () =>
    run("unpublish", async () => {
      options.onUpdated(await call(api.POST("/api/v1/admin/projects/{id}/unpublish", path)));
      options.onNotice("Unpublished. The project is back to draft and off the website.");
    });

  const setState = (state: "archived" | "draft", action: Action, notice: string) =>
    run(action, async () => {
      options.onUpdated(
        await call(
          api.PATCH("/api/v1/admin/projects/{id}", { ...path, body: { publish_state: state } }),
        ),
      );
      options.onNotice(notice);
    });

  const duplicate = () =>
    run("duplicate", async () => {
      const copy = await call(api.POST("/api/v1/admin/projects/{id}/duplicate", path));
      router.push(`${projectPath(copy.id)}?notice=duplicated`);
    });

  const remove = () =>
    run("delete", async () => {
      await call(api.DELETE("/api/v1/admin/projects/{id}", path));
      router.replace(`${PROJECTS_PATH}?notice=deleted`);
    });

  const dialogs = (
    <>
      <ConfirmDialog
        open={confirm === "unpublish"}
        title="Unpublish this project?"
        confirmLabel="Unpublish"
        busy={busy === "unpublish"}
        error={dialogError}
        onCancel={() => setConfirm(null)}
        onConfirm={unpublish}
      >
        It goes back to draft and disappears from the website until it is published again.
      </ConfirmDialog>
      <ConfirmDialog
        open={confirm === "archive"}
        title="Archive this project?"
        confirmLabel="Archive project"
        tone="danger"
        busy={busy === "archive"}
        error={dialogError}
        onCancel={() => setConfirm(null)}
        onConfirm={() =>
          setState("archived", "archive", "Archived. The project is off the website.")
        }
      >
        Archiving removes the project from the website; its leads, media and history stay in the
        CMS.
      </ConfirmDialog>
      <ConfirmDialog
        open={confirm === "delete"}
        title="Delete this draft?"
        confirmLabel="Delete project"
        tone="danger"
        busy={busy === "delete"}
        error={dialogError}
        onCancel={() => setConfirm(null)}
        onConfirm={remove}
      >
        “{project.name}” and its towers, configurations and other details are deleted for good. This
        can&apos;t be undone.
      </ConfirmDialog>
    </>
  );

  return {
    busy,
    publish,
    askUnpublish: () => setConfirm("unpublish"),
    askArchive: () => setConfirm("archive"),
    askDelete: () => setConfirm("delete"),
    restore: () => setState("draft", "restore", "Restored as a draft."),
    duplicate,
    dialogs,
  };
}

export type ProjectActions = ReturnType<typeof useProjectActions>;

/** Where each kind of blocker is fixed, so the checklist can send the user there. */
function tabForBlocker(blocker: string): { tab: string; label: string } | null {
  const text = blocker.toLowerCase();
  if (text.includes("qr")) return { tab: "documents", label: "Go to Documents" };
  if (text.includes("floor plan")) return { tab: "configurations", label: "Go to Configurations" };
  if (text.includes("photo") || text.includes("cover"))
    return { tab: "media", label: "Go to Media" };
  if (text.includes("rera")) return { tab: "details", label: "Go to Details" };
  if (text.includes("configuration"))
    return { tab: "configurations", label: "Go to Configurations" };
  return null;
}

export interface PublishPanelProps {
  project: ProjectAdmin;
  actions: ProjectActions;
  dirty: boolean;
  canWrite: boolean;
  canPublish: boolean;
  canDelete: boolean;
  onGoToTab: (tab: string) => void;
}

export function PublishPanel({
  project,
  actions,
  dirty,
  canWrite,
  canPublish,
  canDelete,
  onGoToTab,
}: PublishPanelProps) {
  const blockers = project.publish_blockers ?? [];
  const state = project.publish_state ?? "draft";
  const card = "flex flex-col gap-2.5 rounded-card border bg-noir-800 p-4.5";
  // SECURITY: taking a live project off the website needs projects.publish (the API checks it
  // too); a content editor can archive drafts only.
  const canArchive = canWrite && (state !== "published" || canPublish);

  return (
    <aside
      aria-label="Publishing"
      className="flex min-w-0 flex-[1_1_300px] flex-col gap-3.5 lg:max-w-[340px]"
    >
      <section
        id="publish-checklist"
        aria-labelledby="publish-title"
        className={`${card} border-gold-line-strong`}
      >
        {state === "published" ? (
          <>
            <h2 id="publish-title" className="text-base font-bold">
              Published
            </h2>
            <p className="text-caption">
              {project.published_at
                ? `On the website since ${formatDateTime(project.published_at)}.`
                : "On the website."}{" "}
              Changes you save show on the website straight away.
            </p>
          </>
        ) : state === "archived" ? (
          <>
            <h2 id="publish-title" className="text-base font-bold">
              Archived
            </h2>
            <p className="text-caption">
              Hidden from the website. Restore it as a draft to work on it again.
            </p>
          </>
        ) : (
          <>
            <h2 id="publish-title" className="text-base font-bold">
              Before you can publish
            </h2>
            {blockers.length === 0 ? (
              <p className="flex items-center gap-2.5 text-small">
                <Mark ok />{" "}
                <span className="font-semibold text-ivory">Nothing is blocking publishing.</span>
              </p>
            ) : (
              <ul className="flex flex-col gap-2" aria-label="What is missing">
                {blockers.map((blocker) => {
                  const fix = tabForBlocker(blocker);
                  return (
                    <li key={blocker} className="flex items-start gap-2.5 text-small">
                      <Mark ok={false} />
                      <span className="flex flex-col">
                        <span className="font-semibold text-ivory">{blocker}</span>
                        {fix ? (
                          <button
                            type="button"
                            onClick={() => onGoToTab(fix.tab)}
                            className="inline-flex min-h-11 items-center self-start text-caption font-bold text-gold-400 underline underline-offset-4"
                          >
                            {fix.label}
                          </button>
                        ) : null}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
            {dirty ? (
              <p className="text-caption font-semibold text-danger">
                Save your changes before publishing.
              </p>
            ) : null}
            <p className="text-xs text-muted">
              Publish stays locked until the RERA number and QR code are both present. Sample
              projects can never be published on the live site.
            </p>
          </>
        )}
      </section>

      {canArchive ? (
        <section aria-labelledby="archive-title" className={`${card} border-line`}>
          <h2 id="archive-title" className="text-base font-bold">
            Archive
          </h2>
          {state === "archived" ? (
            <>
              <p className="text-caption">
                This project is archived. Its leads, media and history stay in the CMS.
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
                Projects with leads are archived, not deleted. Archiving removes the project from
                the website; its leads, media and history stay in the CMS.
              </p>
              <Button variant="danger" className="self-start" onClick={actions.askArchive}>
                Archive project
              </Button>
            </>
          )}
        </section>
      ) : null}

      {canWrite || canDelete ? (
        <section aria-labelledby="copy-title" className={`${card} border-line`}>
          <h2 id="copy-title" className="text-base font-bold">
            Copy or delete
          </h2>
          {canWrite ? (
            <>
              <p className="text-caption">
                Duplicate makes a new draft with this project&apos;s details, towers and
                configurations. Media is not copied: the copy needs its own photos and RERA QR code.
              </p>
              {/* WHY disabled while dirty: Duplicate copies the saved project and opens the
                  copy, so unsaved edits would be left behind on this page. */}
              <Button
                variant="secondary"
                className="self-start"
                loading={actions.busy === "duplicate"}
                disabled={dirty}
                aria-describedby={dirty ? "duplicate-hint" : undefined}
                onClick={actions.duplicate}
              >
                Duplicate
              </Button>
              {dirty ? (
                <p id="duplicate-hint" className="text-caption font-semibold text-danger">
                  Save your changes before duplicating.
                </p>
              ) : null}
            </>
          ) : null}
          {canDelete ? (
            canBeDeleted(project) ? (
              <Button variant="danger" className="self-start" onClick={actions.askDelete}>
                Delete draft
              </Button>
            ) : (
              <p className="text-caption text-muted">
                Only drafts that were never published can be deleted. Archive it instead.
              </p>
            )
          ) : null}
        </section>
      ) : null}
      {actions.dialogs}
    </aside>
  );
}

function Mark({ ok }: { ok: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={`flex size-5 shrink-0 items-center justify-center rounded-pill text-xs font-extrabold ${
        ok ? "bg-palm-line/30 text-palm" : "bg-danger/20 text-danger"
      }`}
    >
      {ok ? "✓" : "✕"}
    </span>
  );
}
