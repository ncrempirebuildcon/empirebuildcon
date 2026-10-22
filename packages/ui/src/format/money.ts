/**
 * Indian rupee display helpers: ₹ 85 L, ₹ 1.25 Cr, ₹ 12,34,567.
 *
 * Money is stored as whole rupees (integers) everywhere (handbook/ARCHITECTURE.md §6); these
 * helpers only format for display. Use them instead of ad-hoc maths (handbook/CODE_STYLE.md §1).
 */

const LAKH = 1_00_000;
const CRORE = 1_00_00_000;

/** Indian digit grouping: 1234567 → "12,34,567". */
const groupIn = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/**
 * Round to at most two decimals and drop trailing zeros: 1.2 → "1.2", 1.25 → "1.25", 78 → "78".
 * WHY: listings read "₹ 78 L", never "₹ 78.00 L"; two decimals keep ₹ 1.25 Cr exact.
 */
function short(value: number): string {
  return (Math.round(value * 100) / 100).toFixed(2).replace(/\.?0+$/, "");
}

/**
 * Formats a rupee amount the way Indian buyers read prices.
 *
 * - Below ₹ 1 lakh: full figure with Indian grouping (`₹ 99,999`).
 * - From ₹ 1 lakh: lakhs (`₹ 85 L`, `₹ 12.35 L`).
 * - From ₹ 1 crore: crores (`₹ 1.25 Cr`).
 *
 * @param amountInr Whole rupees. Negative or non-finite values throw.
 * @returns The display string, with a regular space after ₹.
 */
export function formatInr(amountInr: number): string {
  if (!Number.isFinite(amountInr) || amountInr < 0) {
    throw new RangeError(`formatInr: expected a non-negative amount, got ${amountInr}`);
  }
  if (amountInr < LAKH) return `₹ ${groupIn.format(Math.round(amountInr))}`;
  const lakhs = Math.round((amountInr / LAKH) * 100) / 100;
  // WHY: ₹ 99,99,999 rounds to "100 L"; Indian usage switches to crores at that point.
  if (amountInr >= CRORE || lakhs >= 100) return `₹ ${short(amountInr / CRORE)} Cr`;
  return `₹ ${short(lakhs)} L`;
}

/** Full figure with Indian grouping, for cost sheets and tables: `₹ 12,34,567`. */
export function formatInrFull(amountInr: number): string {
  if (!Number.isFinite(amountInr) || amountInr < 0) {
    throw new RangeError(`formatInrFull: expected a non-negative amount, got ${amountInr}`);
  }
  return `₹ ${groupIn.format(Math.round(amountInr))}`;
}

/**
 * A min–max price range. Equal values show once (handbook/ARCHITECTURE.md §6, "Ranges").
 * Uses an en dash with spaces: `₹ 78 L – ₹ 1.25 Cr`.
 */
export function formatInrRange(minInr: number, maxInr: number): string {
  if (maxInr < minInr) throw new RangeError("formatInrRange: max is below min");
  const lo = formatInr(minInr);
  const hi = formatInr(maxInr);
  return lo === hi ? lo : `${lo} – ${hi}`;
}
