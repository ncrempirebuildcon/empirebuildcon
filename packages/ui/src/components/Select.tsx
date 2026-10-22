/**
 * Select: a labelled native <select> with optional hint and error (handbook/DESIGN_SYSTEM.md §8
 * "Inputs"). Same frame, label and messages as TextField.
 *
 * WHY native: keyboard use, screen readers and the phone's own picker all work without extra code,
 * which a custom listbox would have to rebuild (and test) by hand.
 */
import type { ReactNode, SelectHTMLAttributes } from "react";
import { cx } from "../cx";
import { FieldLabel, FieldMessages, controlClasses, frameClasses, useFieldIds } from "./field";

export interface SelectOption {
  /** Value sent in the form or callback. Use "" for "none". */
  value: string;
  /** Visible text of the option. */
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "id"> {
  /** Visible label above the field. Required: no unlabelled selects. */
  label: ReactNode;
  /** The choices, in order. */
  options: readonly SelectOption[];
  /** Short help text under the field. */
  hint?: ReactNode;
  /** Error message; when set the field is marked invalid. */
  error?: ReactNode;
  /** When set, a first option with value "" and this text (e.g. "Choose a city"). */
  placeholder?: string;
  id?: string;
}

export function Select({
  label,
  options,
  hint,
  error,
  placeholder,
  id,
  className,
  required,
  ...rest
}: SelectProps) {
  const { fieldId, hintId, errorId, describedBy } = useFieldIds(id, hint, error);
  return (
    <div className={cx("flex flex-col gap-1.5", className)}>
      <FieldLabel htmlFor={fieldId} required={required}>
        {label}
      </FieldLabel>
      <div className={frameClasses(error)}>
        <select
          {...rest}
          id={fieldId}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={cx(controlClasses, "cursor-pointer pr-2")}
        >
          {placeholder !== undefined ? <option value="">{placeholder}</option> : null}
          {options.map((option) => (
            <option key={option.value} value={option.value} disabled={option.disabled}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
      <FieldMessages hint={hint} hintId={hintId} error={error} errorId={errorId} />
    </div>
  );
}
