/**
 * Loading placeholder block in `noir-700` (handbook/DESIGN_SYSTEM.md §8 "States": loading
 * skeletons, no shimmer when reduced motion is on). Decorative: hidden from screen readers, so the
 * surrounding region should carry `aria-busy` and a text such as "Loading projects…".
 */
import { cx } from "../cx";

export function Skeleton({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cx(
        "block h-4 animate-pulse rounded-tag bg-noir-700 motion-reduce:animate-none",
        className,
      )}
    />
  );
}
