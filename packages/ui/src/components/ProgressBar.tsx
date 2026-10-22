/**
 * ProgressBar: how far an upload (or any long task) has got, as a thin bar in the gold hairline
 * gradient (DESIGN_SYSTEM §1 "Gold hairline … for progress bars").
 *
 * Accessibility:
 * - `role="progressbar"` with `aria-valuenow` 0–100 and a name (`label`), so screen readers can
 *   read "Uploading tower.jpg, 40 percent". `aria-valuetext` adds the words shown on screen.
 * - With `value={null}` the bar is indeterminate (no `aria-valuenow`), e.g. while a photo is
 *   being resized and there is nothing to measure yet.
 * - The bar is not a live region: announce the start and end of a task in a LiveRegion instead,
 *   so screen readers aren't flooded with every percent.
 */
import { cx } from "../cx";

export interface ProgressBarProps {
  /** Percent done, 0–100, or null when unknown. */
  value: number | null;
  /** Accessible name, e.g. "Uploading tower.jpg". */
  label: string;
  /** Optional words for the current value, e.g. "2.1 of 4.0 MB". */
  valueText?: string;
  className?: string;
}

export function ProgressBar({ value, label, valueText, className }: ProgressBarProps) {
  const percent = value === null ? null : Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent ?? undefined}
      aria-valuetext={valueText ?? (percent === null ? undefined : `${percent}%`)}
      className={cx("h-2 w-full overflow-hidden rounded-pill bg-line", className)}
    >
      <div
        className={cx(
          "h-full rounded-pill bg-[image:var(--gradient-hairline)] transition-[width] duration-200",
          percent === null && "w-1/3 animate-pulse motion-reduce:animate-none",
        )}
        style={percent === null ? undefined : { width: `${percent}%` }}
      />
    </div>
  );
}
