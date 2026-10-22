/**
 * Checkbox for consent and options (handbook/DESIGN_SYSTEM.md §8 "Lead form").
 *
 * COMPLIANCE: consent boxes are never pre-ticked (DPDP Act; handbook/README "Rules that never
 * bend"). This component therefore starts unticked unless the caller passes `checked` from state
 * the visitor set. Do not add a `defaultChecked` default.
 */
import { useId, type InputHTMLAttributes, type ReactNode } from "react";
import { cx } from "../cx";

export interface CheckboxProps extends Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "type" | "id" | "defaultChecked"
> {
  label: ReactNode;
  error?: ReactNode;
  id?: string;
}

export function Checkbox({ label, error, id, className, required, ...rest }: CheckboxProps) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  const errorId = error ? `${fieldId}-error` : undefined;
  return (
    <div className={cx("flex flex-col gap-1", className)}>
      <div className="flex items-start gap-2.5">
        <input
          {...rest}
          id={fieldId}
          type="checkbox"
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={errorId}
          className="mt-0.5 size-5 shrink-0 accent-gold-500"
        />
        <label htmlFor={fieldId} className="text-caption text-ivory">
          {label}
          {required ? " (Required)" : null}
        </label>
      </div>
      {error ? (
        <p id={errorId} className="pl-7.5 text-caption text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
