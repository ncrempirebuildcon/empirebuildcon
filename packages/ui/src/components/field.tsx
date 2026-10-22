/**
 * Shared scaffolding for labelled form controls (Select, Textarea, NumberField): ids, the label
 * above the control, and the hint and error lines under it (handbook/DESIGN_SYSTEM.md §8 "Inputs").
 *
 * Accessibility (WCAG 2.1 AA, DESIGN_SYSTEM §9):
 * - The label is always visible and tied to the control with `htmlFor`.
 * - Hint and error are linked with `aria-describedby`; an error also sets `aria-invalid`.
 * - Borders use `field-line` (#7A6C5B, 3:1 or better); an error switches to `danger`.
 */
import { useId, type ReactNode } from "react";
import { cx } from "../cx";

/** Ids for one field: the control, its hint and its error, plus the joined describedby value. */
export function useFieldIds(id: string | undefined, hint: ReactNode, error: ReactNode) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  const hintId = hint ? `${fieldId}-hint` : undefined;
  const errorId = error ? `${fieldId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return { fieldId, hintId, errorId, describedBy };
}

/** Frame classes shared by every text-like control, so they all look the same. */
export function frameClasses(error: ReactNode, extra?: string): string {
  return cx(
    "flex items-center rounded-input border bg-noir-700",
    error ? "border-danger" : "border-field-line",
    extra,
  );
}

/** Classes for the control itself: 16 px text so iOS Safari does not zoom on focus. */
export const controlClasses =
  "min-h-11 w-full min-w-0 flex-1 rounded-input bg-transparent px-3.5 py-3 text-base text-ivory " +
  "placeholder:text-muted disabled:cursor-not-allowed disabled:opacity-70";

export function FieldLabel({
  htmlFor,
  required,
  children,
}: {
  htmlFor: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <label htmlFor={htmlFor} className="text-small font-semibold text-ivory">
      {children}
      {required ? <span className="font-normal text-muted"> (required)</span> : null}
    </label>
  );
}

export function FieldMessages({
  hint,
  hintId,
  error,
  errorId,
}: {
  hint?: ReactNode;
  hintId?: string;
  error?: ReactNode;
  errorId?: string;
}) {
  return (
    <>
      {hint ? (
        <div id={hintId} className="text-caption text-muted">
          {hint}
        </div>
      ) : null}
      {error ? (
        <p id={errorId} className="text-caption text-danger">
          {error}
        </p>
      ) : null}
    </>
  );
}
