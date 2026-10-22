"use client";
/**
 * The list layout for a project's child items (towers, specifications, location advantages,
 * construction updates, payment plans): a card with an "+ Add …" button, the ordered items with
 * Move up/Move down, Edit and Remove, and an inline form for the item being edited.
 *
 * State lives in `useCollection`; this file only draws it. The configurations table uses the same
 * hook with its own table layout (CollectionForm is shared).
 *
 * Accessibility: item buttons carry the item's name ("Edit Tower A"); moves and saves are
 * announced in a polite live region; the form takes focus when it opens and focus returns to
 * the button that opened it when it closes; Remove asks in a ConfirmDialog.
 */
import { useEffect, useRef, type ReactNode } from "react";
import { Alert, Button, ConfirmDialog, LiveRegion, ReorderButtons } from "@empire/ui";
import type { FieldErrors } from "@/lib/problems";
import { EmptyState, Panel } from "./states";
import type { Collection } from "./useCollection";

export interface CollectionEditorProps<T, D> {
  collection: Collection<T, D>;
  /** Heading of the card, e.g. "Towers and phases". */
  title: string;
  description?: ReactNode;
  /** Button text, e.g. "+ Add tower". */
  addLabel: string;
  /** Shown when there are no items yet. */
  emptyText: string;
  getId: (item: T) => string;
  getLabel: (item: T) => string;
  /** The read-only view of one item in the list. */
  renderSummary: (item: T) => ReactNode;
  /** The form fields for the open draft. */
  renderForm: (draft: D, setDraft: (patch: Partial<D>) => void, errors: FieldErrors) => ReactNode;
  /** False for roles without `projects.write`: no add, edit, remove or move buttons. */
  canWrite: boolean;
  /** Text under the list, e.g. the "approximate road distances" note. */
  footnote?: ReactNode;
  /**
   * Content under an item that stays mounted while the item is edited (e.g. an update's photos
   * with their uploads), because the summary is swapped for the form.
   */
  renderExtra?: (item: T) => ReactNode;
  /** Id prefix for headings and buttons, e.g. "towers". */
  id: string;
}

export function CollectionEditor<T, D>(props: CollectionEditorProps<T, D>) {
  const { collection: c, getId, getLabel, canWrite, id } = props;
  const items = c.ordered;

  return (
    <Panel
      id={id}
      title={props.title}
      description={props.description}
      actions={
        canWrite && c.editing !== "new" ? (
          <Button id={`${id}-add`} variant="secondary" onClick={c.startNew}>
            {props.addLabel}
          </Button>
        ) : null
      }
    >
      {c.listError ? <Alert tone="error">{c.listError}</Alert> : null}
      {items.length === 0 && c.editing !== "new" ? (
        <EmptyState title={props.emptyText} />
      ) : (
        <ol aria-label={props.title} className="flex flex-col gap-2">
          {items.map((item, index) => {
            const editing = c.editingId === getId(item) && c.draft !== null;
            // WHY one <li> with keyed parts: the form replaces only the summary row, so
            // `renderExtra` (keyed) keeps its state, e.g. an upload that is still running.
            return (
              <li
                key={getId(item)}
                className={
                  editing
                    ? "flex flex-col gap-3"
                    : "flex flex-col gap-2 rounded-tile border border-line bg-noir-900 px-3.5 py-2.5"
                }
              >
                {editing && c.draft ? (
                  <CollectionForm
                    key="form"
                    title={`Edit ${getLabel(item)}`}
                    collection={c}
                    returnFocusTo={`${id}-edit-${getId(item)}`}
                  >
                    {props.renderForm(c.draft, c.setDraft, c.errors)}
                  </CollectionForm>
                ) : (
                  <div key="summary" className="flex flex-wrap items-center gap-3">
                    <div className="min-w-0 flex-[1_1_240px]">{props.renderSummary(item)}</div>
                    {canWrite ? (
                      <div className="flex flex-wrap items-center gap-2">
                        <ReorderButtons
                          index={index}
                          count={items.length}
                          itemLabel={getLabel(item)}
                          onMove={c.move}
                          disabled={c.moving}
                        />
                        <Button
                          id={`${id}-edit-${getId(item)}`}
                          variant="secondary"
                          aria-label={`Edit ${getLabel(item)}`}
                          onClick={() => c.startEdit(item)}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="danger"
                          aria-label={`Remove ${getLabel(item)}`}
                          onClick={() => c.askRemove(item)}
                        >
                          Remove
                        </Button>
                      </div>
                    ) : null}
                  </div>
                )}
                {props.renderExtra ? (
                  <div key="extra" className="min-w-0">
                    {props.renderExtra(item)}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ol>
      )}
      {c.editing === "new" && c.draft ? (
        <CollectionForm
          title={props.addLabel.replace(/^\+\s*/, "")}
          collection={c}
          returnFocusTo={`${id}-add`}
        >
          {props.renderForm(c.draft, c.setDraft, c.errors)}
        </CollectionForm>
      ) : null}
      {props.footnote ? <p className="text-caption text-muted">{props.footnote}</p> : null}
      <LiveRegion message={c.message} />
      <RemoveDialog collection={c} getLabel={getLabel} focusAfterRemove={`${id}-add`} />
      <DiscardDialog collection={c} />
    </Panel>
  );
}

/**
 * The confirm step for Remove or Delete (never the browser's confirm()). After a removal the
 * button that opened it is gone, so focus moves to `focusAfterRemove` (usually the Add button)
 * instead of falling back to the page.
 */
export function RemoveDialog<T, D>({
  collection: c,
  getLabel,
  verb = "Remove",
  body = "It is removed from this project straight away. This can't be undone.",
  focusAfterRemove,
}: {
  collection: Collection<T, D>;
  getLabel: (item: T) => string;
  /** "Remove" for a project's items, "Delete" for catalogue rows. */
  verb?: "Remove" | "Delete";
  body?: ReactNode;
  /** Id of the element to focus after a successful removal. */
  focusAfterRemove?: string;
}) {
  useEffect(() => {
    if (c.removedCount === 0 || !focusAfterRemove) return;
    requestAnimationFrame(() => document.getElementById(focusAfterRemove)?.focus());
  }, [c.removedCount, focusAfterRemove]);

  return (
    <ConfirmDialog
      open={c.removing !== null}
      title={c.removing ? `${verb} ${getLabel(c.removing)}?` : `${verb}?`}
      confirmLabel={verb}
      tone="danger"
      busy={c.removeBusy}
      error={c.removeError}
      onCancel={c.cancelRemove}
      onConfirm={c.confirmRemove}
    >
      {body}
    </ConfirmDialog>
  );
}

/**
 * Asks before another item's form replaces an open form with unsaved changes (Edit or Add
 * clicked while editing). "Keep editing" leaves everything as it was.
 */
export function DiscardDialog<T, D>({ collection: c }: { collection: Collection<T, D> }) {
  return (
    <ConfirmDialog
      open={c.pendingOpen}
      title="Discard your changes?"
      confirmLabel="Discard changes"
      cancelLabel="Keep editing"
      tone="danger"
      onCancel={c.keepEditing}
      onConfirm={c.discardAndOpen}
    >
      The form that is open has changes that are not saved yet. Opening another one drops them.
    </ConfirmDialog>
  );
}

/**
 * The add/edit form card: fields from the caller, then Save and Cancel. Takes focus when it
 * opens; gives focus back to `returnFocusTo` (the button that opened it) when it closes.
 */
export function CollectionForm<T, D>({
  title,
  collection: c,
  returnFocusTo,
  children,
}: {
  title: string;
  collection: Collection<T, D>;
  returnFocusTo: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLFormElement>(null);

  useEffect(() => {
    const form = ref.current;
    form?.querySelector<HTMLElement>("input, select, textarea")?.focus();
    return () => {
      // WHY: the opener re-renders after the form closes, so look it up by id a frame later.
      // A form still in the page (React's development double-mount) keeps the focus.
      requestAnimationFrame(() => {
        if (!form?.isConnected) document.getElementById(returnFocusTo)?.focus();
      });
    };
  }, [returnFocusTo]);

  return (
    <form
      ref={ref}
      noValidate
      aria-label={title}
      onSubmit={(event) => {
        event.preventDefault();
        void c.save();
      }}
      className="flex flex-col gap-4 rounded-tile border border-gold-line-strong bg-noir-900 p-4"
    >
      <h3 className="text-base font-bold">{title}</h3>
      {c.formError ? <Alert tone="error">{c.formError}</Alert> : null}
      {/* WHY disabled while saving: the form closes when the save succeeds, so anything typed
          meanwhile would be lost without a word. */}
      <fieldset disabled={c.saving} className="flex min-w-0 flex-col gap-4">
        <legend className="sr-only">{title}</legend>
        {children}
      </fieldset>
      <div className="flex flex-wrap gap-3">
        <Button type="submit" loading={c.saving}>
          Save
        </Button>
        <Button variant="secondary" disabled={c.saving} onClick={c.cancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
