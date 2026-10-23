"use client";
/**
 * Actions on the media attached to one owner and role (a project's photos, a configuration's
 * floor plan, an update's progress photos): order, show/hide on the website, pin the cover,
 * remove from the owner, and edit the item's details. Each saves straight away, then re-reads the
 * owner (`onChanged`) so the lists and the publish checklist come from the server.
 *
 * How it works:
 *   1. Move up/down shows the new order at once (`orderOverride`), saves the full order with
 *      PUT /admin/media-links/order, then re-reads. On failure the saved order comes back and an
 *      error is shown. Focus stays on the Move button of the item that moved.
 *   2. Show/hide and pin/unpin PATCH the link. The API applies the cover rules (one pinned cover
 *      per owner and role, hidden items can't be the cover, hiding the cover unpins it).
 *      Changes run one after another through a queue: a switch flipped while another save runs
 *      waits its turn ("Saving…" on each waiting item) instead of being dropped, and the re-reads
 *      come back in order, so an older answer never overwrites a newer one.
 *   3. Remove asks first (the caller renders ConfirmDialog from `removing`), DELETEs the link and
 *      moves focus to `focusAfterRemove`, because the item's own buttons are gone.
 *
 * The cover is the pinned visible item, else the first visible one (ARCHITECTURE §6 and §12);
 * `coverOf` applies the same rule to show the star without another request.
 */
import { useRef, useState } from "react";
import { moveAnnouncement, moveItem } from "@empire/ui";
import { api, call } from "@/lib/api";
import type { LinkedMedia, Media } from "@/lib/media/upload";
import { problemMessage } from "@/lib/problems";

/** The link id of the cover among `items`: the pinned visible one, else the first visible. */
export function coverOf(items: readonly LinkedMedia[]): string | null {
  const pinned = items.find((item) => item.is_cover && item.is_visible);
  return (pinned ?? items.find((item) => item.is_visible))?.link_id ?? null;
}

/**
 * Id of the wrapper around an item's Move buttons, so focus can return to them after a move.
 * `scope` keeps ids unique when the same list shows on two tabs (Media and Documents).
 */
export const moveButtonsId = (scope: string, linkId: string) => `${scope}-move-${linkId}`;

export interface UseMediaLinksOptions {
  items: readonly LinkedMedia[];
  /** Re-reads the owner after a change. */
  onChanged: () => Promise<unknown>;
  /** What the items are called in messages, e.g. "photo". */
  noun: string;
  /** Element to focus after an item is removed (usually the uploader's button). */
  focusAfterRemove: string;
  /** Prefix for element ids (see moveButtonsId). */
  scope: string;
}

export function useMediaLinks({
  items,
  onChanged,
  noun,
  focusAfterRemove,
  scope,
}: UseMediaLinksOptions) {
  const [orderOverride, setOrderOverride] = useState<string[] | null>(null);
  const [moving, setMoving] = useState(false);
  // Link ids with a change queued or saving (step 2).
  const [pending, setPending] = useState<ReadonlySet<string>>(() => new Set());
  const queue = useRef<Promise<void>>(Promise.resolve());
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [removing, setRemoving] = useState<LinkedMedia | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const [editing, setEditing] = useState<LinkedMedia | null>(null);

  const byId = new Map(items.map((item) => [item.link_id, item] as const));
  const ordered = orderOverride
    ? orderOverride.map((id) => byId.get(id)).filter((item): item is LinkedMedia => !!item)
    : [...items];

  async function refresh(failure: string) {
    try {
      await onChanged();
    } catch {
      setError(failure);
    }
  }

  async function move(from: number, to: number, direction: "up" | "down") {
    const item = ordered[from];
    if (!item || moving) return;
    const next = moveItem(ordered, from, to);
    setOrderOverride(next.map((i) => i.link_id));
    setMessage(moveAnnouncement(item.title, to, next.length));
    setError(null);
    setMoving(true);
    try {
      await call(
        api.PUT("/api/v1/admin/media-links/order", { body: { ids: next.map((i) => i.link_id) } }),
      ); // 1
      await onChanged();
    } catch (err) {
      setError(problemMessage(err, "Couldn't save the new order. The saved order is shown."));
      await onChanged().catch(() => undefined);
    } finally {
      setOrderOverride(null);
      setMoving(false);
      // WHY: React may re-insert the moved card, which drops focus; put it back on the same
      // button (it stays focusable at the ends of the list, ReorderButtons uses aria-disabled).
      requestAnimationFrame(() => {
        const buttons = document.getElementById(moveButtonsId(scope, item.link_id));
        buttons?.querySelectorAll<HTMLButtonElement>("button")[direction === "up" ? 0 : 1]?.focus();
      });
    }
  }

  function setPendingFor(linkId: string, on: boolean) {
    setPending((current) => {
      const next = new Set(current);
      if (on) next.add(linkId);
      else next.delete(linkId);
      return next;
    });
  }

  function patchLink(item: LinkedMedia, body: { is_visible?: boolean; is_cover?: boolean }) {
    // The item's own controls are busy while its change waits, so one item never queues twice.
    if (pending.has(item.link_id)) return;
    setPendingFor(item.link_id, true);
    setError(null);
    queue.current = queue.current.then(async () => {
      try {
        await call(
          api.PATCH("/api/v1/admin/media-links/{id}", {
            params: { path: { id: item.link_id } },
            body,
          }),
        ); // 2
        setMessage(linkMessage(item, body, noun));
        await refresh("Saved, but the list couldn't be refreshed. Reload the page to see it.");
      } catch (err) {
        setError(problemMessage(err, `Couldn't change ${item.title}.`));
      } finally {
        setPendingFor(item.link_id, false);
      }
    });
  }

  async function confirmRemove() {
    if (!removing || removeBusy) return;
    setRemoveBusy(true);
    setRemoveError(null);
    try {
      await call(
        api.DELETE("/api/v1/admin/media-links/{id}", {
          params: { path: { id: removing.link_id } },
        }),
      ); // 3
    } catch (err) {
      setRemoveError(problemMessage(err, `Couldn't remove the ${noun}.`));
      setRemoveBusy(false);
      return;
    }
    await refresh("Removed, but the list couldn't be refreshed. Reload the page.");
    setMessage(`${removing.title} was removed. It stays in the media library.`);
    setRemoving(null);
    setRemoveBusy(false);
    requestAnimationFrame(() => document.getElementById(focusAfterRemove)?.focus());
  }

  return {
    ordered,
    moving,
    /** True while a change to this link waits or saves. */
    isPending: (linkId: string) => pending.has(linkId),
    error,
    message,
    move,
    setVisible: (item: LinkedMedia, visible: boolean) => patchLink(item, { is_visible: visible }),
    setPinned: (item: LinkedMedia, pinned: boolean) => patchLink(item, { is_cover: pinned }),
    removing,
    askRemove: (item: LinkedMedia) => {
      setRemoveError(null);
      setRemoving(item);
    },
    cancelRemove: () => setRemoving(null),
    confirmRemove,
    removeBusy,
    removeError,
    editing,
    edit: (item: LinkedMedia) => setEditing(item),
    closeEdit: () => setEditing(null),
    /** After the details dialog saved: announce it and re-read the owner. */
    detailsSaved: async (media: Media) => {
      const nowShowable = editing !== null && !editing.is_visible && media.label !== null;
      setMessage(
        nowShowable
          ? `Details of ${media.title} were saved. Switch on Show on website to show it.`
          : `Details of ${media.title} were saved.`,
      );
      await refresh("Saved, but the list couldn't be refreshed. Reload the page to see it.");
    },
  };
}

export type MediaLinks = ReturnType<typeof useMediaLinks>;

function linkMessage(
  item: LinkedMedia,
  body: { is_visible?: boolean; is_cover?: boolean },
  noun: string,
): string {
  if (body.is_visible === true) return `${item.title} is shown on the website.`;
  if (body.is_visible === false) return `${item.title} is hidden from the website.`;
  if (body.is_cover === true) return `${item.title} is now the cover ${noun}.`;
  return `${item.title} is no longer pinned as the cover. The first shown ${noun} is the cover.`;
}
