/**
 * FormattedTextEditor: a labelled textarea for WhatsApp-style text with the formatting hint, a
 * character count and a live preview drawn by `<FormattedText>` (the same renderer the website
 * uses in Phase 5), so staff see exactly how bullets and bold will look before saving.
 *
 * Accessibility (WCAG 2.1 AA, DESIGN_SYSTEM §9):
 * - The label is visible; the hint and the count are linked to the textarea with
 *   `aria-describedby` (through Textarea), and the count is in words, not colour.
 * - The preview is a labelled group ("Preview of Answer"). WHY not a live region: it changes on
 *   every key press, and reading it aloud each time would drown out typing.
 */
import { useId, type ReactNode } from "react";
import { cx } from "../cx";
import { FormattedText } from "./FormattedText";
import { Textarea } from "./Textarea";

/** The formatting reminder shown under every formatted-text field. */
export const FORMATTING_HINT =
  "Formatting: *bold* · _italic_ · - bullet (two spaces before the dash to nest) · blank line for a new paragraph";

export interface FormattedTextEditorProps {
  /** Visible label, e.g. "Answer". Required; also names the preview ("Preview of Answer"). */
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** Maximum length in characters (the API's limit). The count shows "n / limit characters". */
  limit: number;
  /** Extra help before the formatting hint. */
  hint?: ReactNode;
  /** Error message from validation or the API. */
  error?: ReactNode;
  rows?: number;
  id?: string;
  required?: boolean;
  disabled?: boolean;
  placeholder?: string;
  /** Hides the preview (e.g. in a narrow dialog); the hint and count stay. */
  hidePreview?: boolean;
  className?: string;
}

/** "120 / 4,000 characters", plus "· too long" past the limit (words, not only colour). */
export function lengthText(value: string, limit: number): string {
  // WHY code points: "₹" and Hindi letters count as one character each, as staff expect.
  const length = [...value].length;
  const base = `${length.toLocaleString("en-IN")} / ${limit.toLocaleString("en-IN")} characters`;
  return length > limit ? `${base} · too long` : base;
}

export function FormattedTextEditor({
  label,
  value,
  onChange,
  limit,
  hint,
  error,
  rows = 6,
  id,
  required,
  disabled,
  placeholder,
  hidePreview = false,
  className,
}: FormattedTextEditorProps) {
  const previewId = useId();
  const over = [...value].length > limit;
  return (
    <div className={cx("flex min-w-0 flex-col gap-3", className)}>
      <Textarea
        id={id}
        label={label}
        rows={rows}
        value={value}
        required={required}
        disabled={disabled}
        placeholder={placeholder}
        maxLength={limit}
        onChange={(event) => onChange(event.target.value)}
        error={error}
        hint={
          <span className="flex flex-col gap-0.5">
            {hint ? <span>{hint}</span> : null}
            <span>{FORMATTING_HINT}</span>
            <span className={over ? "text-danger" : undefined}>{lengthText(value, limit)}</span>
          </span>
        }
      />
      {hidePreview ? null : (
        <div
          role="group"
          aria-labelledby={`${previewId}-title`}
          className="flex min-w-0 flex-col gap-2 rounded-tile border border-line bg-noir-900 p-3.5 text-small text-body"
        >
          <p id={`${previewId}-title`} className="text-xs font-bold tracking-[0.08em] text-muted">
            <span aria-hidden="true">PREVIEW</span>
            <span className="sr-only">Preview of {label}</span>
          </p>
          <FormattedText
            text={value}
            empty={<p className="text-muted">Nothing to preview yet.</p>}
          />
        </div>
      )}
    </div>
  );
}
