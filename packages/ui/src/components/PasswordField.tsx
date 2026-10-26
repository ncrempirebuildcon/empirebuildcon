/**
 * PasswordField: a labelled password input with a Show/Hide button inside the field frame
 * (board NoirCmsLogin). Used for signing in, choosing a password from a setup or reset link, and
 * changing one's own password.
 *
 * Accessibility (WCAG 2.1 AA, DESIGN_SYSTEM §9):
 * - The toggle is a real <button> with `aria-pressed`, named "Show password" / "Hide password",
 *   at least 44 px tall, and never submits the form.
 * - Hint and error are linked with `aria-describedby` (TextField does it).
 *
 * SECURITY: the value is never copied anywhere else (no title, no storage, no logs). Showing the
 * password only switches the input's type; `autoComplete` tells password managers whether this
 * is the current password or a new one.
 */
import { useState } from "react";
import { TextField, type TextFieldProps } from "./TextField";

export interface PasswordFieldProps extends Omit<TextFieldProps, "type" | "trailing"> {
  /**
   * "current-password" to sign in or confirm, "new-password" when choosing one (password managers
   * then offer to generate and save it). Required, so every field says which it is.
   */
  autoComplete: "current-password" | "new-password";
  /** Words used in the toggle's name, e.g. "new password" → "Show new password". */
  toggleNoun?: string;
}

export function PasswordField({
  autoComplete,
  toggleNoun = "password",
  ...rest
}: PasswordFieldProps) {
  const [shown, setShown] = useState(false);
  return (
    <TextField
      {...rest}
      type={shown ? "text" : "password"}
      autoComplete={autoComplete}
      // WHY: phones would otherwise capitalise or "correct" a password shown as text.
      autoCapitalize="none"
      autoCorrect="off"
      spellCheck={false}
      trailing={
        <button
          type="button"
          onClick={() => setShown((value) => !value)}
          aria-pressed={shown}
          aria-label={`${shown ? "Hide" : "Show"} ${toggleNoun}`}
          className="min-h-11 rounded-input px-3 text-small font-bold text-gold-400 hover:text-gold-300"
        >
          {shown ? "Hide" : "Show"}
        </button>
      }
    />
  );
}
