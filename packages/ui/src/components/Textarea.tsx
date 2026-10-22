/**
 * Textarea: a labelled multi-line field with optional hint and error (handbook/DESIGN_SYSTEM.md
 * §8 "Inputs"). Same frame, label and messages as TextField; the user can resize it vertically.
 *
 * Pair it with `CharacterCount` as the hint when a soft limit matters (e.g. SEO descriptions).
 */
import type { ReactNode, TextareaHTMLAttributes } from "react";
import { cx } from "../cx";
import { FieldLabel, FieldMessages, frameClasses, useFieldIds } from "./field";

export interface TextareaProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "id"> {
  /** Visible label above the field. Required. */
  label: ReactNode;
  /** Short help text under the field. */
  hint?: ReactNode;
  /** Error message; when set the field is marked invalid. */
  error?: ReactNode;
  id?: string;
}

export function Textarea({
  label,
  hint,
  error,
  id,
  className,
  required,
  rows = 4,
  ...rest
}: TextareaProps) {
  const { fieldId, hintId, errorId, describedBy } = useFieldIds(id, hint, error);
  return (
    <div className={cx("flex flex-col gap-1.5", className)}>
      <FieldLabel htmlFor={fieldId} required={required}>
        {label}
      </FieldLabel>
      <div className={frameClasses(error)}>
        <textarea
          {...rest}
          id={fieldId}
          rows={rows}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={
            "min-h-11 w-full min-w-0 resize-y rounded-input bg-transparent px-3.5 py-3 text-base " +
            "text-ivory placeholder:text-muted disabled:cursor-not-allowed disabled:opacity-70"
          }
        />
      </div>
      <FieldMessages hint={hint} hintId={hintId} error={error} errorId={errorId} />
    </div>
  );
}

export interface CharacterCountProps {
  /** The current text. */
  value: string;
  /** Recommended maximum, e.g. 60 for a search title. */
  limit: number;
}

/**
 * "56 / 60 characters · good", or "· too long" in the danger colour past the limit (design board
 * NoirCmsProject, SEO tab). Text carries the state, so colour is never the only signal.
 */
export function CharacterCount({ value, limit }: CharacterCountProps) {
  // WHY: count code points, not UTF-16 units, so "₹" and Hindi letters count as one each.
  const length = [...value].length;
  if (length === 0) {
    return <span>0 / {limit} characters</span>;
  }
  const over = length > limit;
  return (
    <span className={over ? "text-danger" : "text-palm"}>
      {length} / {limit} characters · {over ? "too long" : "good"}
    </span>
  );
}
