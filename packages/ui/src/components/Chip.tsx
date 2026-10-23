/**
 * Status chip (handbook/DESIGN_SYSTEM.md §8 "Chips"). Every chip carries a text label, so colour
 * is never the only signal (WCAG 1.4.1).
 *
 * The `stage…` variants are the lead pipeline stages from the CMS boards (NoirCmsLeads,
 * NoirCmsDashboard), drawn with the `stage-*` tokens: New, Contacted, Site visit, Negotiation,
 * Booked, Lost. Their contrast is in DESIGN_SYSTEM §9 (Booked 9.9:1, Lost 11.6:1).
 */
import type { ReactNode } from "react";
import { cx } from "../cx";

export type ChipVariant =
  | "upcoming"
  | "ongoing"
  | "completed"
  | "available"
  | "soldOut"
  | "offMarket"
  | "sample"
  | "draft"
  | "scheduled"
  | "published"
  | "archived"
  | "stageNew"
  | "stageContacted"
  | "stageSiteVisit"
  | "stageNegotiation"
  | "stageBooked"
  | "stageLost";

const styles: Record<ChipVariant, string> = {
  upcoming: "text-ivory border border-line-strong",
  ongoing: "text-gold-300 border border-gold-500/60",
  completed: "text-palm border border-palm-line",
  available: "text-palm border border-palm-line",
  soldOut: "bg-danger-bg text-danger-on-bg",
  offMarket: "bg-noir-700 text-muted",
  sample: "text-danger border border-danger",
  draft: "text-muted border border-line-strong",
  scheduled: "text-gold-300 border border-gold-500/60",
  published: "text-palm border border-palm-line",
  archived: "bg-noir-700 text-muted",
  stageNew: "text-stage-new-text border border-stage-new-border",
  stageContacted: "text-stage-contacted-text border border-stage-contacted-border",
  stageSiteVisit: "text-stage-site-visit-text border border-stage-site-visit-border",
  stageNegotiation: "bg-stage-negotiation-bg text-stage-negotiation-text",
  stageBooked: "bg-stage-booked-bg text-stage-booked-text",
  stageLost: "bg-stage-lost-bg text-stage-lost-text",
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
