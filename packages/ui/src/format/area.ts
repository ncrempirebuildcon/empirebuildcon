/**
 * Area helpers: carpet area shown first, in sq ft and sq m (handbook/DESIGN_SYSTEM.md §3).
 *
 * COMPLIANCE: RERA requires carpet area to be shown. Every project, property and ad view shows
 * both units through `formatArea`, so the two figures can never disagree on screen.
 */

/** Square feet → square metres factor (1 sq ft = 0.092903 sq m, exact to 6 places). */
export const SQM_PER_SQFT = 0.092903;

/**
 * Square feet to square metres, rounded to one decimal: 980 → 91.0.
 * WHY: one decimal matches how RERA certificates and buyers quote metric carpet area.
 */
export function sqftToSqm(sqft: number): number {
  return Math.round(sqft * SQM_PER_SQFT * 10) / 10;
}

/** Square metres to whole square feet: 91.04 → 980. */
export function sqmToSqft(sqm: number): number {
  return Math.round(sqm / SQM_PER_SQFT);
}

const groupIn = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/**
 * Formats an area as `980 sq ft · 91.0 sq m`.
 *
 * @param value The area in `unit`.
 * @param unit  `"sqft"` (default) or `"sqm"`. The database stores square metres
 *              (handbook/ARCHITECTURE.md §6); designs and RERA documents often quote sq ft.
 */
export function formatArea(value: number, unit: "sqft" | "sqm" = "sqft"): string {
  if (!Number.isFinite(value) || value < 0) {
    throw new RangeError(`formatArea: expected a non-negative area, got ${value}`);
  }
  const sqft = unit === "sqft" ? Math.round(value) : sqmToSqft(value);
  const sqm = unit === "sqm" ? Math.round(value * 10) / 10 : sqftToSqm(value);
  return `${groupIn.format(sqft)} sq ft · ${sqm.toFixed(1)} sq m`;
}

/** A carpet-area range, e.g. `720 – 1,120 sq ft · 66.9 – 104.1 sq m`. Equal values show once. */
export function formatAreaRange(min: number, max: number, unit: "sqft" | "sqm" = "sqft"): string {
  if (max < min) throw new RangeError("formatAreaRange: max is below min");
  if (min === max) return formatArea(min, unit);
  const toSqft = (v: number) => (unit === "sqft" ? Math.round(v) : sqmToSqft(v));
  const toSqm = (v: number) => (unit === "sqm" ? Math.round(v * 10) / 10 : sqftToSqm(v));
  return (
    `${groupIn.format(toSqft(min))} – ${groupIn.format(toSqft(max))} sq ft · ` +
    `${toSqm(min).toFixed(1)} – ${toSqm(max).toFixed(1)} sq m`
  );
}
