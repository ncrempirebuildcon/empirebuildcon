/**
 * NumberField: a labelled text input for whole rupees, areas, percentages and coordinates.
 *
 * How it works:
 *   1. The parent owns the number (`value`, `null` when empty) and gets every valid change through
 *      `onValueChange`. Money stays an integer (handbook/CODE_STYLE.md §4): with `decimals={0}`
 *      only digits are accepted.
 *   2. While the field has focus the user's own text is kept as typed ("78,00,000" or "7800000"),
 *      so the caret never jumps.
 *   3. On blur the text is rebuilt from the number: whole numbers use Indian grouping
 *      ("78,00,000") unless `grouping` is off.
 *
 * WHY type="text" with inputMode instead of type="number": number inputs reject grouping commas,
 * change the value on mouse-wheel scroll and read badly with screen readers.
 */
import { useState, type InputHTMLAttributes, type ReactNode } from "react";
import { cx } from "../cx";
import { FieldLabel, FieldMessages, controlClasses, frameClasses, useFieldIds } from "./field";

const groupIn = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

export interface NumberFieldProps extends Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "id" | "value" | "defaultValue" | "onChange" | "type" | "inputMode" | "prefix"
> {
  /** Visible label above the field. Include the unit, e.g. "Carpet area (sq ft)". */
  label: ReactNode;
  /** The number, or `null` when the field is empty. */
  value: number | null;
  /** Called with the new number (or `null` when cleared) on every valid keystroke. */
  onValueChange: (value: number | null) => void;
  /** Decimal places allowed. 0 (default) accepts whole numbers only. */
  decimals?: number;
  /** Allow a leading minus sign (coordinates). Default false. */
  allowNegative?: boolean;
  /** Group whole numbers the Indian way when not editing. Default true when `decimals` is 0. */
  grouping?: boolean;
  /** Short text before the number inside the frame, e.g. "₹" or "≈". Decorative. */
  prefix?: ReactNode;
  /** Short text after the number inside the frame, e.g. "sq ft" or "%". Decorative. */
  suffix?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  id?: string;
}

/**
 * Parses what the user typed. Returns `null` for an empty field, `undefined` while the text is
 * not a number yet ("-", "." or too many decimals), else the number.
 */
export function parseNumberInput(
  text: string,
  decimals = 0,
  allowNegative = false,
): number | null | undefined {
  const cleaned = text.replace(/[,\s]/g, "");
  if (cleaned === "") return null;
  const sign = allowNegative ? "-?" : "";
  const fraction = decimals > 0 ? `(\\.\\d{0,${decimals}})?` : "";
  if (!new RegExp(`^${sign}\\d+${fraction}$`).test(cleaned)) return undefined;
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : undefined;
}

/** The text shown for a number when the field is not being edited. */
export function formatNumberInput(value: number | null, grouping: boolean): string {
  if (value === null) return "";
  return grouping && Number.isInteger(value) ? groupIn.format(value) : String(value);
}

export function NumberField({
  label,
  value,
  onValueChange,
  decimals = 0,
  allowNegative = false,
  grouping,
  prefix,
  suffix,
  hint,
  error,
  id,
  className,
  required,
  onFocus,
  onBlur,
  ...rest
}: NumberFieldProps) {
  const { fieldId, hintId, errorId, describedBy } = useFieldIds(id, hint, error);
  const useGrouping = grouping ?? decimals === 0;
  // `draft` holds the user's own text while the field has focus; null means "show the value".
  const [draft, setDraft] = useState<string | null>(null);
  const text = draft ?? formatNumberInput(value, useGrouping);

  return (
    <div className={cx("flex flex-col gap-1.5", className)}>
      <FieldLabel htmlFor={fieldId} required={required}>
        {label}
      </FieldLabel>
      <div className={frameClasses(error)}>
        {prefix ? (
          <span aria-hidden="true" className="pl-3.5 text-muted">
            {prefix}
          </span>
        ) : null}
        <input
          {...rest}
          id={fieldId}
          type="text"
          inputMode={decimals > 0 ? "decimal" : "numeric"}
          autoComplete="off"
          required={required}
          value={text}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          onFocus={(event) => {
            setDraft(formatNumberInput(value, useGrouping));
            onFocus?.(event);
          }}
          onChange={(event) => {
            setDraft(event.target.value);
            const parsed = parseNumberInput(event.target.value, decimals, allowNegative);
            if (parsed !== undefined) onValueChange(parsed);
          }}
          onBlur={(event) => {
            setDraft(null);
            onBlur?.(event);
          }}
          className={cx(controlClasses, "tabular-nums", prefix ? "pl-2" : undefined)}
        />
        {suffix ? (
          <span aria-hidden="true" className="pr-3.5 text-small whitespace-nowrap text-muted">
            {suffix}
          </span>
        ) : null}
      </div>
      <FieldMessages hint={hint} hintId={hintId} error={error} errorId={errorId} />
    </div>
  );
}
