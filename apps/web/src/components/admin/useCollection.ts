"use client";
/**
 * State for editing a project's child list (towers, configurations, specifications, location
 * advantages, construction updates, payment plans): add, edit, remove and reorder, each saved
 * straight away through its own API call.
 *
 * How it works:
 *   1. One item at a time is open in a form (`editing` is "new", an item id, or null). The form
 *      edits a `draft`; Save calls `create` or `update`, then `onChanged` re-reads the project so
 *      the list, the publish blockers and the order come from the server.
 *   2. Remove asks first (the caller renders ConfirmDialog from `removing`).
 *   3. Move up/down shows the new order at once (`orderOverride`), saves the full order with
 *      `reorder`, then re-reads; on failure the server order comes back and an error is shown.
 *   4. `dirty` is true while an open form differs from where it started, for the "unsaved
 *      changes" warning. Opening another item (Edit or Add) while the open form is dirty asks
 *      first (`pendingOpen`, shown by the caller's DiscardDialog), so changes are never dropped
 *      silently.
 */
import { useState } from "react";
import { moveAnnouncement, moveItem } from "@empire/ui";
import { fieldErrors, problemMessage, type FieldErrors } from "@/lib/problems";

export interface CollectionOptions<T, D> {
  items: readonly T[];
  getId: (item: T) => string;
  /** Short name of an item for buttons and messages, e.g. "Tower A". */
  getLabel: (item: T) => string;
  emptyDraft: () => D;
  toDraft: (item: T) => D;
  /** Checks done before calling the API; return messages by field (empty when all is well). */
  validate?: (draft: D) => Partial<Record<string, string>>;
  create: (draft: D) => Promise<unknown>;
  update: (id: string, draft: D) => Promise<unknown>;
  remove: (id: string) => Promise<unknown>;
  reorder: (ids: string[]) => Promise<unknown>;
  /** Re-read the project after a change. */
  onChanged: () => Promise<unknown>;
  /** Singular noun for messages, e.g. "tower". */
  noun: string;
}

type Editing = null | "new" | { id: string };

export function useCollection<T, D>(options: CollectionOptions<T, D>) {
  const { items, getId, getLabel, noun } = options;
  const [editing, setEditing] = useState<Editing>(null);
  const [draft, setDraftState] = useState<D | null>(null);
  const [initial, setInitial] = useState<string>("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState<T | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);
  // Counts successful removals, so the dialog can move focus once the removed row is gone.
  const [removedCount, setRemovedCount] = useState(0);
  const [orderOverride, setOrderOverride] = useState<string[] | null>(null);
  const [moving, setMoving] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  // The form the user asked to open while the current one had unsaved changes.
  const [pendingOpen, setPendingOpen] = useState<{ next: Editing; start: D } | null>(null);

  const byId = new Map(items.map((item) => [getId(item), item] as const));
  const ordered = orderOverride
    ? orderOverride.map((id) => byId.get(id)).filter((item): item is T => item !== undefined)
    : [...items];

  function open(next: Editing, start: D) {
    setEditing(next);
    setDraftState(start);
    setInitial(JSON.stringify(start));
    setErrors({});
    setFormError(null);
  }

  const dirty = draft !== null && JSON.stringify(draft) !== initial;

  /** Opens a form, or asks first when the open one has unsaved changes. */
  function request(next: Editing, start: D) {
    if (saving) return;
    if (dirty) setPendingOpen({ next, start });
    else open(next, start);
  }

  function close() {
    setEditing(null);
    setDraftState(null);
    setErrors({});
    setFormError(null);
  }

  async function save() {
    if (!draft || saving) return;
    const found: FieldErrors = {};
    for (const [field, message] of Object.entries(options.validate?.(draft) ?? {})) {
      if (message) found[field] = message;
    }
    if (Object.keys(found).length > 0) {
      setErrors(found);
      setFormError("Some fields need attention.");
      return;
    }
    setSaving(true);
    setErrors({});
    setFormError(null);
    setListError(null);
    try {
      if (editing === "new") await options.create(draft);
      else if (editing) await options.update(editing.id, draft);
    } catch (err) {
      setErrors(fieldErrors(err));
      setFormError(problemMessage(err, `Couldn't save the ${noun}.`));
      setSaving(false);
      return;
    }
    // WHY separate: the item is saved at this point, so a failed re-read must not invite the
    // user to save it again (that would add it twice).
    try {
      await options.onChanged();
    } catch {
      setListError("Saved, but the list couldn't be refreshed. Reload the page to see it.");
    }
    setMessage(editing === "new" ? `The ${noun} was added.` : `Changes to the ${noun} were saved.`);
    close();
    setSaving(false);
  }

  async function confirmRemove() {
    if (!removing || removeBusy) return;
    setRemoveBusy(true);
    setRemoveError(null);
    const id = getId(removing);
    try {
      await options.remove(id);
    } catch (err) {
      setRemoveError(problemMessage(err, `Couldn't remove the ${noun}.`));
      setRemoveBusy(false);
      return;
    }
    try {
      await options.onChanged();
    } catch {
      setListError("Removed, but the list couldn't be refreshed. Reload the page.");
    }
    setMessage(`${getLabel(removing)} was removed.`);
    if (editing !== null && editing !== "new" && editing.id === id) close();
    setRemoving(null);
    setRemovedCount((n) => n + 1);
    setRemoveBusy(false);
  }

  async function move(from: number, to: number) {
    const item = ordered[from];
    if (!item || moving) return;
    const next = moveItem(ordered, from, to);
    setOrderOverride(next.map(getId));
    setMessage(moveAnnouncement(getLabel(item), to, next.length));
    setListError(null);
    setMoving(true);
    try {
      await options.reorder(next.map(getId));
      await options.onChanged();
    } catch (err) {
      setListError(problemMessage(err, "Couldn't save the new order. The saved order is shown."));
      await options.onChanged().catch(() => undefined);
    } finally {
      setOrderOverride(null);
      setMoving(false);
    }
  }

  return {
    ordered,
    editing,
    editingId: editing && editing !== "new" ? editing.id : null,
    draft,
    setDraft: (patch: Partial<D>) =>
      setDraftState((current) => (current ? { ...current, ...patch } : current)),
    errors,
    formError,
    saving,
    dirty,
    startNew: () => request("new", options.emptyDraft()),
    startEdit: (item: T) => request({ id: getId(item) }, options.toDraft(item)),
    /** Set while asking whether to drop the open form's changes (see DiscardDialog). */
    pendingOpen: pendingOpen !== null,
    discardAndOpen: () => {
      if (pendingOpen) open(pendingOpen.next, pendingOpen.start);
      setPendingOpen(null);
    },
    keepEditing: () => setPendingOpen(null),
    cancel: close,
    save,
    removing,
    askRemove: (item: T) => {
      setRemoveError(null);
      setRemoving(item);
    },
    cancelRemove: () => setRemoving(null),
    confirmRemove,
    removeBusy,
    removeError,
    removedCount,
    move,
    moving,
    listError,
    message,
  };
}

export type Collection<T, D> = ReturnType<typeof useCollection<T, D>>;
