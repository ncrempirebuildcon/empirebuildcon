/**
 * Status chip (handbook/DESIGN_SYSTEM.md §8 "Chips"). Every chip carries a text label, so colour
 * is never the only signal (WCAG 1.4.1).
 */
import type { ReactNode } from "react";
import { cx } from "../cx";

export type ChipVariant =
  "ongoing" | "completed" | "soldOut" | "sample" | "draft" | "scheduled" | "published" | "archived";

const styles: Record<ChipVariant, string> = {
  ongoing: "text-gold-300 border border-gold-500/60",
  completed: "text-palm border border-palm-line",
  soldOut: "bg-danger-bg text-danger-on-bg",
  sample: "text-danger border border-danger",
  draft: "text-muted border border-line-strong",
  scheduled: "text-gold-300 border border-gold-500/60",
  published: "text-palm border border-palm-line",
  archived: "bg-noir-700 text-muted",
};

export interface ChipProps {
  variant: ChipVariant;
  /** Visible text, e.g. "Under construction". Required: chips are never colour-only. */
  children: ReactNode;
  className?: string;
}

export function Chip({ variant, children, className }: ChipProps) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-pill px-2.5 py-1 text-xs font-bold leading-none",
        styles[variant],
        className,
      )}
    >
      {children}
    </span>
  );
}
