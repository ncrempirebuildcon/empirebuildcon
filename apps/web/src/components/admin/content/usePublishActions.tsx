"use client";
/**
 * Publish, Unpublish, Archive, Restore and Delete for a page or a post, with their confirm
 * dialogs (never the browser's confirm()). The caller supplies the API calls; this hook runs
 * one at a time, shows errors in the dialog or the editor, and words the dialogs.
 *
 * Rules (ARCHITECTURE §6, spec Phase 4 part 4 §3–4): only drafts that were never published can
 * be deleted; published or archived items are archived instead. A refused publish (409, e.g. a
 * legal page still marked DRAFT in production) re-reads the item so its blockers are current.
 * SECURITY: the caller shows the buttons only with the right permission; the API checks again.
 */
import { useState } from "react";
import { useRouter } from "next/navigation";
import { ConfirmDialog } from "@empire/ui";
import { problemMessage, toProblem } from "@/lib/problems";

type Action = "publish" | "unpublish" | "archive" | "restore" | "delete";
type Confirmable = "unpublish" | "archive" | "delete";

export interface PublishCalls<T> {
  publish: () => Promise<T>;
  unpublish: () => Promise<T>;
  setState: (state: "archived" | "draft") => Promise<T>;
  remove: () => Promise<unknown>;
}

export interface PublishActionsOptions<T> {
  /** "page" or "post", for the dialogs and messages. */
  noun: "page" | "post";
  /** The item's title, quoted in the delete dialog. */
  title: string;
  calls: PublishCalls<T>;
  /** Where to go after a delete (the list, with a notice). */
  afterDelete: string;
  onUpdated: (item: T) => void;
  refresh: () => Promise<unknown>;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}

export function usePublishActions<T>(options: PublishActionsOptions<T>) {
  const { noun } = options;
  const router = useRouter();
  const [busy, setBusy] = useState<Action | null>(null);
  const [confirm, setConfirm] = useState<Confirmable | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const Noun = noun === "page" ? "Page" : "Post";

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
        options.onUpdated(await options.calls.publish());
        options.onNotice(`Published. The ${noun} is live.`);
      } catch (err) {
        if (toProblem(err).status === 409) await options.refresh().catch(() => undefined);
        throw err;
      }
    });

  const unpublish = () =>
    run("unpublish", async () => {
      options.onUpdated(await options.calls.unpublish());
      options.onNotice(`Unpublished. The ${noun} is back to draft and off the website.`);
    });

  const setState = (state: "archived" | "draft", action: Action, notice: string) =>
    run(action, async () => {
      options.onUpdated(await options.calls.setState(state));
      options.onNotice(notice);
    });

  const remove = () =>
    run("delete", async () => {
      await options.calls.remove();
      router.replace(options.afterDelete);
    });

  const dialogs = (
    <>
      <ConfirmDialog
        open={confirm === "unpublish"}
        title={`Unpublish this ${noun}?`}
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
        title={`Archive this ${noun}?`}
        confirmLabel={`Archive ${noun}`}
        tone="danger"
        busy={busy === "archive"}
        error={dialogError}
        onCancel={() => setConfirm(null)}
        onConfirm={() =>
          setState("archived", "archive", `Archived. The ${noun} is off the website.`)
        }
      >
        Archiving removes the {noun} from the website; its content and history stay in the CMS, and
        it can be restored as a draft.
      </ConfirmDialog>
      <ConfirmDialog
        open={confirm === "delete"}
        title={`Delete this draft ${noun}?`}
        confirmLabel={`Delete ${noun}`}
        tone="danger"
        busy={busy === "delete"}
        error={dialogError}
        onCancel={() => setConfirm(null)}
        onConfirm={remove}
      >
        {Noun} “{options.title}” is deleted for good. This can&apos;t be undone.
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
    dialogs,
  };
}

export type PublishActions = ReturnType<typeof usePublishActions>;
