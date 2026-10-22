/**
 * Dialog: a modal for a short form, e.g. "Photo details" (title, alt text, honest label) in the
 * media manager. For yes/no questions use ConfirmDialog instead.
 *
 * How it works:
 *   1. A native <dialog> opened with showModal(): the browser traps focus, makes the page behind
 *      inert, and returns focus to the element that opened it when it closes.
 *   2. The first field (or `[data-autofocus]`) takes focus when it opens.
 *   3. Escape asks the parent to close (`onClose`), except while `busy`, so a save can't be
 *      interrupted half-way.
 *
 * Accessibility: labelled by its visible title (`aria-labelledby`); the caller puts the Save and
 * Cancel buttons in `footer` with real labels ("Save details", never "OK").
 */
import { useEffect, useId, useRef, type FormEvent, type ReactNode } from "react";
import { cx } from "../cx";

export interface DialogProps {
  /** Whether the dialog is shown. */
  open: boolean;
  /** Visible heading, e.g. "Photo details". */
  title: ReactNode;
  /** The form fields. */
  children: ReactNode;
  /** The buttons under the fields (a submit button submits the form). */
  footer: ReactNode;
  /** Called when the form is submitted (Enter in a field, or a submit button). */
  onSubmit: () => void;
  /** Called on Escape or a Cancel button; not while busy. */
  onClose: () => void;
  /** Blocks Escape while a save runs. */
  busy?: boolean;
  /** Wider dialog for previews (default 28 rem). */
  wide?: boolean;
  className?: string;
}

export function Dialog({
  open,
  title,
  children,
  footer,
  onSubmit,
  onClose,
  busy = false,
  wide = false,
  className,
}: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      // WHY: jsdom (unit tests) has no showModal(); the open attribute is the closest stand-in.
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
      const first =
        dialog.querySelector<HTMLElement>("[data-autofocus]") ??
        dialog.querySelector<HTMLElement>("input, select, textarea");
      first?.focus();
    } else if (!open && dialog.open) {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
      className={cx(
        "m-auto w-[calc(100%-32px)] rounded-card border border-gold-line-strong bg-noir-800 p-0",
        "text-body backdrop:bg-noir-900/85",
        wide ? "max-w-2xl" : "max-w-md",
        className,
      )}
    >
      {open ? (
        <form
          noValidate
          aria-labelledby={titleId}
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            if (!busy) onSubmit();
          }}
          className="flex max-h-[calc(100dvh-48px)] flex-col gap-4 overflow-y-auto p-6"
        >
          <h2 id={titleId} className="text-h3 font-bold text-ivory">
            {title}
          </h2>
          {children}
          <div className="flex flex-wrap justify-end gap-3">{footer}</div>
        </form>
      ) : null}
    </dialog>
  );
}
