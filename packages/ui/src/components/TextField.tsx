/**
 * TextField: labelled input with optional hint and error (handbook/DESIGN_SYSTEM.md §8 "Inputs").
 *
 * - The label sits above the field and is always visible (no placeholder-only labels).
 * - Hint and error are linked with `aria-describedby`; an error also sets `aria-invalid`.
 * - Border uses `field-line` (#7A6C5B) for 3:1 contrast; error uses `danger`.
 * - Font size is 16 px so iOS Safari does not zoom on focus.
 */
import { useId, type InputHTMLAttributes, type ReactNode } from "react";
import { cx } from "../cx";

export interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: ReactNode;
  /** Short help text shown under the field. */
  hint?: ReactNode;
  /** Error message; when set the field is marked invalid. */
  error?: ReactNode;
  /** Extra element inside the field frame on the right (e.g. a show/hide password button). */
  trailing?: ReactNode;
  id?: string;
}

export function TextField({
  label,
  hint,
  error,
  trailing,
  id,
  className,
  required,
  ...rest
}: TextFieldProps) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  const hintId = hint ? `${fieldId}-hint` : undefined;
  const errorId = error ? `${fieldId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className={cx("flex flex-col gap-1.5", className)}>
      <label htmlFor={fieldId} className="text-small font-semibold text-ivory">
        {label}
        {required ? <span className="text-muted font-normal"> (required)</span> : null}
      </label>
      <div
        className={cx(
          "flex items-center rounded-input border bg-noir-700",
          error ? "border-danger" : "border-field-line",
        )}
      >
        <input
          {...rest}
          id={fieldId}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className="min-h-11 w-full min-w-0 flex-1 rounded-input bg-transparent px-3.5 py-3 text-base text-ivory placeholder:text-muted"
        />
        {trailing ? <div className="pr-1.5">{trailing}</div> : null}
      </div>
      {hint ? (
        <p id={hintId} className="text-caption text-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="text-caption text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
