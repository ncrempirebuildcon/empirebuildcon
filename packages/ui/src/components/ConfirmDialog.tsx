/**
 * ConfirmDialog: asks before an action that is hard to undo (delete, archive, unpublish).
 * It replaces the browser's `confirm()`, which cannot be styled, reads poorly with screen readers
 * and is blocked inside some embedded browsers.
 *
 * How it works:
 *   1. A native <dialog> opened with showModal(): the browser traps focus, makes the page behind
 *      it inert, closes on Escape and returns focus to the button that opened it.
 *   2. "Cancel" gets focus first, so pressing Enter by habit never confirms a destructive action.
 *   3. While `busy`, both buttons and Escape are ignored, so the action cannot run twice.
 *
 * Accessibility: labelled by its title and described by its message (`aria-labelledby`,
 * `aria-describedby`); an error from the action is shown inside the dialog with role="alert".
 */
import { useEffect, useId, useRef, type ReactNode } from "react";
import { Alert } from "./Alert";
import { Button } from "./Button";

export interface ConfirmDialogProps {
  /** Whether the dialog is shown. */
  open: boolean;
  /** Short question, e.g. "Delete this draft?". */
  title: ReactNode;
  /** What will happen, in plain words. */
  children: ReactNode;
  /** Text of the confirm button, e.g. "Delete project". Say the action, never "OK". */
  confirmLabel: string;
  /** Text of the cancel button. Default "Cancel". */
  cancelLabel?: string;
  /** "danger" shows the confirm button in the danger style (delete, archive). */
  tone?: "danger" | "default";
  /** Shows a spinner on the confirm button and blocks closing while the action runs. */
  busy?: boolean;
  /** Error from the last attempt, shown inside the dialog. */
  error?: ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  cancelLabel = "Cancel",
  tone = "default",
  busy = false,
  error,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const bodyId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      // WHY: jsdom (unit tests) has no showModal(); the open attribute is the closest stand-in.
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
      dialog.querySelector<HTMLButtonElement>("[data-autofocus]")?.focus();
    } else if (!open && dialog.open) {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      aria-describedby={bodyId}
      onCancel={(event) => {
        // Escape: let the parent decide (it closes by setting open=false), never while busy.
        event.preventDefault();
        if (!busy) onCancel();
      }}
      className={
        "m-auto w-[calc(100%-32px)] max-w-md rounded-card border border-gold-line-strong " +
        "bg-noir-800 p-6 text-body backdrop:bg-noir-900/85"
      }
    >
      {open ? (
        <div className="flex flex-col gap-4">
          <h2 id={titleId} className="text-h3 font-bold text-ivory">
            {title}
          </h2>
          <div id={bodyId} className="text-small">
            {children}
          </div>
          {error ? <Alert tone="error">{error}</Alert> : null}
          <div className="flex flex-wrap justify-end gap-3">
            <Button variant="secondary" data-autofocus disabled={busy} onClick={onCancel}>
              {cancelLabel}
            </Button>
            <Button
              variant={tone === "danger" ? "danger" : "primary"}
              loading={busy}
              onClick={onConfirm}
            >
              {confirmLabel}
            </Button>
          </div>
        </div>
      ) : null}
    </dialog>
  );
}
