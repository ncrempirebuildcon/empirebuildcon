/**
 * OneTimeCodeField: the 6-digit code from an authenticator app (board NoirCmsLogin, "Two-factor
 * check"): one wide input with large, spaced digits, not six separate boxes.
 *
 * WHY one input and not six boxes: six inputs break pasting, autofill from the phone's
 * keyboard ("From Messages" / password managers), and screen readers announce six unlabelled
 * fields. One input keeps all of that working.
 *
 * Accessibility (WCAG 2.1 AA, DESIGN_SYSTEM §9):
 * - `autocomplete="one-time-code"` and `inputmode="numeric"` (number keypad on phones); never
 *   `type="number"`, which drops leading zeros and adds spin buttons.
 * - Spaces, dashes and other non-digits typed or pasted ("123 456") are removed as you type, so
 *   the field never shows an error for a harmless format.
 * - Label above, hint and error linked with `aria-describedby` (TextField does it).
 *
 * SECURITY: the code is a secret for 30 seconds; it is never stored or logged by this component.
 */
import { TextField, type TextFieldProps } from "./TextField";

export interface OneTimeCodeFieldProps extends Omit<
  TextFieldProps,
  "type" | "value" | "onChange" | "inputMode" | "autoComplete" | "maxLength"
> {
  /** The digits typed so far (0 to `length`). */
  value: string;
  /** Called with the digits only, at most `length` of them. */
  onValueChange: (digits: string) => void;
  /** How many digits the code has. Defaults to 6 (RFC 6238 codes in authenticator apps). */
  length?: number;
}

/** Only the digits of `text`, at most `length` of them ("123 456" → "123456"). */
export function codeDigits(text: string, length = 6): string {
  return text.replace(/\D/g, "").slice(0, length);
}

export function OneTimeCodeField({
  value,
  onValueChange,
  length = 6,
  className,
  ...rest
}: OneTimeCodeFieldProps) {
  return (
    <TextField
      {...rest}
      type="text"
      inputMode="numeric"
      autoComplete="one-time-code"
      // WHY no maxLength: a pasted "123 456" is 7 characters; the digits are cut to `length`
      // in onChange instead, so the paste isn't truncated to "123 45".
      pattern={`[0-9]{${length}}`}
      spellCheck={false}
      value={value}
      onChange={(event) => onValueChange(codeDigits(event.target.value, length))}
      className={className}
      // WHY `!`: the input's own `text-base` would otherwise compete with the larger size.
      inputClassName="text-center text-[26px]! font-semibold tracking-[0.5em] tabular-nums"
    />
  );
}
