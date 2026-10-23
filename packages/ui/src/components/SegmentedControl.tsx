/**
 * SegmentedControl: a small set of mutually exclusive views drawn as pills, like the media
 * manager's "Photos · 8 / Videos · 1 / Documents · 3" switcher (board NoirCmsProject).
 *
 * Accessibility (WAI-ARIA Authoring Practices "Radio Group"):
 * - `role="radiogroup"` with a name, and one `role="radio"` button per option with
 *   `aria-checked`.
 * - Only the checked option is in the Tab order (roving tabindex); Arrow keys, Home and End move
 *   to and select another option, exactly like native radio buttons.
 * - Each option shows text, so the selection never relies on colour alone.
 */
import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { cx } from "../cx";

export interface SegmentedOption<V extends string> {
  value: V;
  label: ReactNode;
}

export interface SegmentedControlProps<V extends string> {
  /** Accessible name of the group, e.g. "Media type". */
  label: string;
  options: readonly SegmentedOption<V>[];
  value: V;
  onChange: (value: V) => void;
  className?: string;
}

export function SegmentedControl<V extends string>({
  label,
  options,
  value,
  onChange,
  className,
}: SegmentedControlProps<V>) {
  const refs = useRef(new Map<V, HTMLButtonElement>());

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const last = options.length - 1;
    const forward = event.key === "ArrowRight" || event.key === "ArrowDown";
    const back = event.key === "ArrowLeft" || event.key === "ArrowUp";
    const target = forward
      ? index === last
        ? 0
        : index + 1
      : back
        ? index === 0
          ? last
          : index - 1
        : event.key === "Home"
          ? 0
          : event.key === "End"
            ? last
            : null;
    if (target === null) return;
    event.preventDefault();
    const next = options[target];
    if (!next) return;
    onChange(next.value);
    refs.current.get(next.value)?.focus();
  }

  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={cx(
        "flex flex-wrap gap-1.5 rounded-pill border border-line bg-noir-900 p-1",
        className,
      )}
    >
      {options.map((option, index) => {
        const checked = option.value === value;
        return (
          <button
            key={option.value}
            ref={(node) => {
              if (node) refs.current.set(option.value, node);
              else refs.current.delete(option.value);
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            onClick={() => onChange(option.value)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={cx(
              // WHY smaller on phones: three options fit on one line at 390 px.
              "min-h-11 rounded-pill px-2.5 text-caption whitespace-nowrap transition-colors duration-150 sm:px-4 sm:text-small",
              checked
                ? "bg-gold-500 font-extrabold text-noir-900"
                : "font-semibold text-body hover:text-gold-300",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
