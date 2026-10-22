/**
 * Honest image labels (DESIGN_SYSTEM §7 "Every image is labelled for what it is"; board
 * NoirCmsProject media cards): artist's impression, actual photo, or progress photo with its
 * month. The website shows the label on every image, so a render is never passed off as a photo.
 *
 * COMPLIANCE: honest content is a rule that never bends (handbook README, D-002). The CMS asks
 * for a label on every photo and says plainly when one is missing; it never guesses a label.
 */
import type { Schema } from "@/lib/api";

export type HonestLabel = NonNullable<Schema<"Media">["label"]>;

/**
 * Labels that carry a month: a progress photo must (the API refuses one without), an actual
 * photo may. An artist's impression is not of any particular month, so it never has one.
 */
export const DATED_LABELS: ReadonlySet<HonestLabel> = new Set(["actual_photo", "progress_photo"]);

export const HONEST_LABEL: Record<HonestLabel, string> = {
  artist_impression: "Artist's impression",
  actual_photo: "Actual photo",
  progress_photo: "Progress photo",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** "Sep 2026" for a first-of-month date ("2026-09-01"). */
export function formatLabelMonth(isoDate: string): string {
  const [year, month] = isoDate.split("-").map(Number);
  return `${MONTHS[(month ?? 1) - 1]} ${year}`;
}

/** The label as shown on a card: "Artist's impression", "Progress photo · Sep 2026", or null. */
export function honestLabelText(
  label: HonestLabel | null | undefined,
  month: string | null | undefined,
): string | null {
  if (!label) return null;
  if (month && DATED_LABELS.has(label))
    return `${HONEST_LABEL[label]} · ${formatLabelMonth(month)}`;
  return HONEST_LABEL[label];
}

/** Text colour per label, as on the board (actual photos green, progress gold). */
export const HONEST_LABEL_TONE: Record<HonestLabel, string> = {
  artist_impression: "text-body",
  actual_photo: "text-palm",
  progress_photo: "text-gold-300",
};

/** The first day of a month as the API stores it: (2026, 9) → "2026-09-01". */
export const firstOfMonth = (year: number, month: number) =>
  `${year}-${String(month).padStart(2, "0")}-01`;

/** The month of a calendar date as a first-of-month date: "2026-09-30" → "2026-09-01". */
export const monthOf = (isoDate: string) => `${isoDate.slice(0, 7)}-01`;
