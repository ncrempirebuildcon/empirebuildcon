/**
 * EMI calculation helpers for property pages (handbook/tasks/phase-5/5.7b-tools.md).
 *
 * How it works (CODE_STYLE §2.3 money logic):
 *   1. Loan amount P in whole rupees, annual interest rate, and tenure in years (or months) are provided.
 *   2. Standard reducing-balance formula:
 *        EMI = P · r · (1 + r)^n / ((1 + r)^n − 1)
 *      where r = annualRate / 12 / 100 is the monthly rate, and n is the total number of monthly instalments.
 *   3. Edge cases: for 0% interest rate (or infinitesimal rate < 1e-9 % per month), EMI = P / n.
 *   4. For loans with interest (r > 0), total paid is the sum of rounded monthly instalments (monthlyEmi * n) and total interest is max(0, totalPaid - P); for 0% loans, total paid is strictly P and total interest is 0.
 *   5. All monetary outputs are formatted in whole rupees with Indian number grouping.
 *   6. Out-of-bounds inputs are strictly refused with descriptive errors (no silent clamping).
 *
 * Collaborators: Antigravity <noreply@google.com>, Claude (reviews 1 & 2). Decisions: D-040, D-049.
 */

export const EMI_LIMITS = {
  MIN_PRINCIPAL: 1,
  MAX_PRINCIPAL: 100_00_00_000, // ₹ 100 Crore
  MIN_TENURE_YEARS: 5,
  MAX_TENURE_YEARS: 30,
  DEFAULT_TENURE_YEARS: 20,
  MIN_RATE: 6.0,
  MAX_RATE: 15.0,
  DEFAULT_RATE: 8.5,
  RATE_STEP: 0.05,
} as const;

export interface EmiCalculationParams {
  /** Principal loan amount in whole rupees (P > 0). */
  principal: number;
  /** Annual interest rate as a percentage (e.g. 8.5 for 8.5%). Must be >= 0. */
  annualRatePercent: number;
  /** Tenure in years (e.g. 20). If provided without tenureMonths, n = tenureYears * 12. */
  tenureYears?: number;
  /** Tenure in months directly (e.g. 1 to 360). */
  tenureMonths?: number;
}

export interface EmiResult {
  /** Monthly EMI in whole rupees (rounded to nearest integer). */
  monthlyEmi: number;
  /** Total interest payable over the entire tenure in whole rupees. */
  totalInterest: number;
  /** Total amount payable (principal + interest) in whole rupees. */
  totalPaid: number;
  /** Tenure in months. */
  months: number;
  /** Tenure in years. */
  years: number;
  /** Raw unrounded monthly EMI. */
  rawMonthlyEmi: number;
}

/**
 * Calculates reducing-balance EMI, total interest, and total payment.
 * Throws RangeError / TypeError if inputs are outside permissible limits.
 */
export function calculateEmi({
  principal,
  annualRatePercent,
  tenureYears,
  tenureMonths,
}: EmiCalculationParams): EmiResult {
  if (
    !Number.isFinite(principal) ||
    principal < EMI_LIMITS.MIN_PRINCIPAL ||
    !Number.isInteger(principal)
  ) {
    throw new RangeError(
      `calculateEmi: principal must be a positive integer >= ${EMI_LIMITS.MIN_PRINCIPAL}, got ${principal}`,
    );
  }
  if (principal > EMI_LIMITS.MAX_PRINCIPAL) {
    throw new RangeError(
      `calculateEmi: principal exceeds maximum limit of ₹ ${EMI_LIMITS.MAX_PRINCIPAL}, got ${principal}`,
    );
  }
  if (!Number.isFinite(annualRatePercent) || annualRatePercent < 0 || annualRatePercent > 100) {
    throw new RangeError(
      `calculateEmi: annualRatePercent must be between 0 and 100, got ${annualRatePercent}`,
    );
  }

  let n: number;
  let yrs: number;
  if (tenureMonths !== undefined) {
    if (
      !Number.isFinite(tenureMonths) ||
      tenureMonths < 1 ||
      !Number.isInteger(tenureMonths) ||
      tenureMonths > 600
    ) {
      throw new RangeError(
        `calculateEmi: tenureMonths must be an integer between 1 and 600, got ${tenureMonths}`,
      );
    }
    n = tenureMonths;
    yrs = tenureMonths / 12;
  } else if (tenureYears !== undefined) {
    if (
      !Number.isFinite(tenureYears) ||
      !Number.isInteger(tenureYears) ||
      tenureYears < 1 ||
      tenureYears > 50
    ) {
      throw new RangeError(
        `calculateEmi: tenureYears must be an integer between 1 and 50, got ${tenureYears}`,
      );
    }
    n = tenureYears * 12;
    yrs = tenureYears;
  } else {
    throw new TypeError("calculateEmi: either tenureYears or tenureMonths must be provided");
  }

  const P = principal;
  const r = annualRatePercent / 100 / 12;

  // Zero interest rate or infinitesimal rate (< 1e-11 monthly, ~1e-9 % per month)
  // WHY: avoids catastrophic cancellation / division by zero in floating point exponentiation.
  if (annualRatePercent === 0 || r < 1e-11) {
    const rawMonthly = P / n;
    const monthlyEmi = Math.round(rawMonthly);
    // WHY: for 0% loans, total interest is strictly 0 and total paid is the principal P,
    // avoiding rounding artifacts (e.g. ₹278 × 360 = ₹1,00,080 for a ₹1,00,000 loan).
    const totalPaid = P;
    const totalInterest = 0;
    return {
      monthlyEmi,
      totalInterest,
      totalPaid,
      months: n,
      years: yrs,
      rawMonthlyEmi: rawMonthly,
    };
  }

  // Monthly interest rate reducing-balance formula
  const factor = Math.pow(1 + r, n);
  const rawMonthly = (P * r * factor) / (factor - 1);
  const monthlyEmi = Math.round(rawMonthly);
  const totalPaid = monthlyEmi * n;
  const totalInterest = Math.max(0, totalPaid - P);

  return {
    monthlyEmi,
    totalInterest,
    totalPaid,
    months: n,
    years: yrs,
    rawMonthlyEmi: rawMonthly,
  };
}

/**
 * Validates whether a tenure in years is within the allowed UI limits (5 to 30 years).
 */
export function isTenureYearsValid(years: number): boolean {
  return (
    Number.isFinite(years) &&
    Number.isInteger(years) &&
    years >= EMI_LIMITS.MIN_TENURE_YEARS &&
    years <= EMI_LIMITS.MAX_TENURE_YEARS
  );
}

/**
 * Validates whether an interest rate is an exact multiple of the 0.05% step.
 */
export function isRateStepValid(rate: number): boolean {
  if (!Number.isFinite(rate)) return false;
  const steps = Math.round(rate / EMI_LIMITS.RATE_STEP);
  return Math.abs(steps * EMI_LIMITS.RATE_STEP - rate) < 1e-4;
}

/**
 * Validates whether an interest rate is within the allowed UI limits (6.00% to 15.00%)
 * and respects the 0.05% step (values off the step are refused).
 */
export function isRateValid(rate: number): boolean {
  return (
    Number.isFinite(rate) &&
    rate >= EMI_LIMITS.MIN_RATE &&
    rate <= EMI_LIMITS.MAX_RATE &&
    isRateStepValid(rate)
  );
}
