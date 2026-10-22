/**
 * Switch: an on/off control that saves straight away, drawn like the CMS boards' "Show on
 * website · Shown" toggle (NoirCmsProject, media cards): a small track with a knob, then the
 * label and the current state in words.
 *
 * Accessibility (WCAG 2.1 AA, DESIGN_SYSTEM §9):
 * - A real <button role="switch"> with `aria-checked`, so it works with the keyboard (Space and
 *   Enter) and screen readers announce "on" or "off".
 * - The state is also written out ("Shown" / "Hidden"), so colour is never the only signal.
 * - `context` adds words only screen readers hear (e.g. the photo's title), so a list of
 *   switches doesn't read as "Show on website" ten times. The visible words stay at the start of
 *   the accessible name (WCAG 2.5.3 Label in Name): "Show on website · Shown: Tower A".
 *   WHY an aria-label then, not a visually hidden span: browsers put a space before an
 *   absolutely positioned span when they build the name ("Shown : Tower A").
 * - The whole row is the target and at least 44 px tall.
 * - `busy` and `disabled` use `aria-disabled`, so focus stays on the switch while a save runs.
 */
import { cx } from "../cx";

export interface SwitchProps {
  /** Whether the switch is on. */
  checked: boolean;
  /** Called with the new value when the user flips it. Not called while busy or disabled. */
  onChange: (checked: boolean) => void;
  /** Visible label, e.g. "Show on website". Required: no unlabelled switches. */
  label: string;
  /** The state in words after the label, e.g. { on: "Shown", off: "Hidden" }. Optional. */
  stateText?: { on: string; off: string };
  /** Extra words for screen readers only, e.g. the item's title. */
  context?: string;
  /** Blocks flipping and shows the switch dimmed (e.g. no permission). */
  disabled?: boolean;
  /** A save is running: flipping is blocked and `aria-busy` is set. */
  busy?: boolean;
  id?: string;
  className?: string;
  /** Id of an element that explains the switch (e.g. why it can't be changed). */
  "aria-describedby"?: string;
}

export function Switch({
  checked,
  onChange,
  label,
  stateText,
  context,
  disabled = false,
  busy = false,
  id,
  className,
  "aria-describedby": describedBy,
}: SwitchProps) {
  const inactive = disabled || busy;
  const visible = stateText ? `${label} · ${checked ? stateText.on : stateText.off}` : label;
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={context ? `${visible}: ${context}` : undefined}
      aria-disabled={inactive || undefined}
      aria-busy={busy || undefined}
      aria-describedby={describedBy}
      onClick={() => {
        // WHY: aria-disabled keeps focus on the switch but does not block clicks by itself.
        if (!inactive) onChange(!checked);
      }}
      className={cx(
        "inline-flex min-h-11 items-center gap-2 text-left text-caption font-semibold text-body",
        inactive && "cursor-not-allowed opacity-60",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cx(
          "flex h-5 w-8.5 shrink-0 items-center rounded-pill border px-0.5 transition-colors duration-150",
          checked
            ? "justify-end border-palm-line bg-palm-line/35"
            : "justify-start border-line-strong bg-noir-700",
        )}
      >
        <span className={cx("size-3.5 rounded-pill", checked ? "bg-palm" : "bg-muted")} />
      </span>
      <span>{visible}</span>
    </button>
  );
}
