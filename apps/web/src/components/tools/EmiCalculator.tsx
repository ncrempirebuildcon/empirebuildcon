"use client";

/**
 * EMI Calculator client component (handbook/tasks/phase-5/5.7b-tools.md).
 *
 * Requirements:
 *   - Inputs:
 *       1. Loan amount in whole rupees with Indian grouping (NumberField).
 *          Prefilled from the home's lowest price when shown, empty when price is on request.
 *       2. Tenure: 5 to 30 years (Select with all options).
 *       3. Interest rate: 6.00 to 15.00 % a year, steps of 0.05, defaulting to 8.50 %.
 *          Out of bounds or off-step rates are refused with visible error (not clamped).
 *   - Outputs:
 *       Monthly EMI, total interest, total paid, and number of months.
 *       Reducing-balance formula: EMI = P · r · (1+r)^n / ((1+r)^n − 1), with 0% giving P/n.
 *       Amounts formatted in ₹ with Indian grouping, rounded to whole rupees (formatInrFull).
 *   - Honesty:
 *       - Rate field says "sample rate, check with your bank".
 *       - Prefilled loan amount notes price exclusions and that banks lend less.
 *       - Note: "Indicative only, not a loan offer. Your bank decides the amount, rate and tenure."
 *       - No bank names, no fake urgency or lowest-EMI claims.
 *   - Progressive enhancement: renders formula and note when JavaScript is disabled.
 *
 * Collaborators: Antigravity <noreply@google.com>, Claude (reviews 1 & 2). Decisions: D-040, D-049.
 */
import { useEffect, useId, useRef, useState } from "react";
import { formatInrFull, NumberField, Select } from "@empire/ui";
import {
  calculateEmi,
  EMI_LIMITS,
  isRateStepValid,
  isRateValid,
  isTenureYearsValid,
  type EmiResult,
} from "@/lib/tools/emi";
import { useMounted } from "@/lib/tools/mounted";

export interface EmiCalculatorProps {
  /** Pre-filled price in whole rupees, or null/undefined when on request. */
  defaultPriceInr?: number | null;
  /** Whether the price is on request. */
  priceOnRequest?: boolean;
}

const TENURE_OPTIONS = Array.from(
  { length: EMI_LIMITS.MAX_TENURE_YEARS - EMI_LIMITS.MIN_TENURE_YEARS + 1 },
  (_, idx) => {
    const yrs = idx + EMI_LIMITS.MIN_TENURE_YEARS;
    return {
      value: String(yrs),
      label: `${yrs} years (${yrs * 12} months)`,
    };
  },
);

export function EmiCalculator({ defaultPriceInr, priceOnRequest }: EmiCalculatorProps) {
  const isMounted = useMounted();

  const isPrefilled =
    !priceOnRequest &&
    defaultPriceInr !== undefined &&
    defaultPriceInr !== null &&
    defaultPriceInr > 0;
  const initialPrincipal = isPrefilled ? Math.round(defaultPriceInr) : null;

  const [loanAmount, setLoanAmount] = useState<number | null>(initialPrincipal);
  const [tenureYears, setTenureYears] = useState<number>(EMI_LIMITS.DEFAULT_TENURE_YEARS);
  const [ratePercent, setRatePercent] = useState<number | null>(EMI_LIMITS.DEFAULT_RATE);
  const [liveAnnouncement, setLiveAnnouncement] = useState<string>("");
  const isTouchedRef = useRef(false);

  const tenureId = useId();
  const rateId = useId();
  const loanId = useId();

  // Validate loan amount (Should 8)
  let loanError: string | undefined;
  if (loanAmount !== null) {
    if (loanAmount < EMI_LIMITS.MIN_PRINCIPAL) {
      loanError = "Enter a loan amount greater than ₹ 0";
    } else if (loanAmount > EMI_LIMITS.MAX_PRINCIPAL) {
      loanError = "Enter an amount up to ₹ 100 crore";
    }
  }

  // Validate rate: strictly refuse out-of-bounds or off-step rates without silent clamping (Must 1)
  let rateError: string | undefined;
  if (ratePercent !== null) {
    if (ratePercent < EMI_LIMITS.MIN_RATE || ratePercent > EMI_LIMITS.MAX_RATE) {
      rateError = `Enter a rate between ${EMI_LIMITS.MIN_RATE.toFixed(2)}% and ${EMI_LIMITS.MAX_RATE.toFixed(2)}%`;
    } else if (!isRateStepValid(ratePercent)) {
      rateError = "Rate must be in steps of 0.05% (e.g. 8.50%)";
    }
  }

  // Calculate EMI only when both inputs are valid and have no errors
  let emiResult: EmiResult | null = null;
  const isInputValid =
    loanAmount !== null &&
    !loanError &&
    ratePercent !== null &&
    !rateError &&
    isTenureYearsValid(tenureYears) &&
    isRateValid(ratePercent);

  if (isInputValid) {
    try {
      emiResult = calculateEmi({
        principal: loanAmount,
        annualRatePercent: ratePercent,
        tenureYears,
      });
    } catch {
      emiResult = null;
    }
  }

  const monthlyEmi = emiResult?.monthlyEmi;

  // Debounced screen reader live announcement for monthly EMI (Should 1 & 9)
  // WHY: announces nothing on page load until the visitor touches an input;
  // announces errors when present instead of clearing the region.
  useEffect(() => {
    const timer = setTimeout(() => {
      if (!isTouchedRef.current) return;

      if (loanError) {
        setLiveAnnouncement(loanError);
      } else if (rateError) {
        setLiveAnnouncement(rateError);
      } else if (monthlyEmi !== undefined) {
        setLiveAnnouncement(`Monthly EMI ${formatInrFull(monthlyEmi)}`);
      } else {
        setLiveAnnouncement("");
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [monthlyEmi, loanError, rateError]);

  if (!isMounted) {
    // Progressive enhancement: when JavaScript is disabled, render formula and note instead
    return (
      <section id="emi" aria-labelledby="emi-heading" className="flex flex-col gap-6">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 id="emi-heading" className="font-display text-h2 font-semibold text-body">
            EMI calculator
          </h2>
          <span className="text-caption font-semibold uppercase tracking-[0.08em] text-gold-400">
            Sample rates · check with your bank
          </span>
        </div>

        <div
          className="flex flex-col gap-3 rounded-card border border-gold-line bg-noir-800 p-6 text-body"
          data-testid="emi-nojs-fallback"
        >
          <p className="font-semibold text-gold-300">Standard reducing-balance formula:</p>
          <code className="block rounded-tile border border-gold-line/40 bg-noir-900 p-3 font-mono text-small text-gold-300">
            EMI = P · r · (1 + r)ⁿ / ((1 + r)ⁿ − 1)
          </code>
          <p className="text-small text-muted">
            Where <strong>P</strong> is the loan amount, <strong>r</strong> is the monthly interest
            rate (annual rate / 12 / 100), and <strong>n</strong> is the tenure in months. For 0%
            interest rate, EMI = P / n.
          </p>
          <p className="border-t border-gold-line/30 pt-3 text-caption text-muted">
            Sample rates, check with your bank. Indicative only, not a loan offer. Your bank decides
            the amount, rate and tenure.
          </p>
        </div>
      </section>
    );
  }

  // Loan amount hint: prefilled price note (Should 12)
  let loanHint = "Whole rupees with Indian digit grouping";
  if (isPrefilled && loanAmount === initialPrincipal) {
    loanHint =
      "Prefilled with the lowest listed price, which excludes GST, stamp duty and registration. Banks usually lend less than the full price.";
  } else if (priceOnRequest && (loanAmount === null || loanAmount <= 0)) {
    loanHint = "Enter a loan amount to calculate estimated EMI";
  }

  return (
    <section id="emi" aria-labelledby="emi-heading" className="flex flex-col gap-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="emi-heading" className="font-display text-h2 font-semibold text-body">
          EMI calculator
        </h2>
        <span className="text-caption font-semibold uppercase tracking-[0.08em] text-gold-400">
          Sample rates · check with your bank
        </span>
      </div>

      {/* Screen reader polite live region for debounced EMI result (Should 9) */}
      <div aria-live="polite" className="sr-only" data-testid="emi-live-announcement">
        {liveAnnouncement}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.3fr_1fr]">
        {/* Form controls */}
        <div className="flex flex-col gap-5 rounded-card border border-line bg-noir-800 p-5 md:p-6">
          <NumberField
            id={loanId}
            label="Loan amount"
            value={loanAmount}
            onValueChange={(val) => {
              isTouchedRef.current = true;
              setLoanAmount(val);
            }}
            prefix={priceOnRequest && (!loanAmount || loanAmount <= 0) ? undefined : "₹"}
            error={loanError}
            hint={loanHint}
          />

          <Select
            id={tenureId}
            label="Tenure"
            value={String(tenureYears)}
            options={TENURE_OPTIONS}
            onChange={(e) => {
              isTouchedRef.current = true;
              const val = parseInt(e.target.value, 10);
              if (Number.isFinite(val)) setTenureYears(val);
            }}
            hint="5 to 30 years (60 to 360 months)"
          />

          <NumberField
            id={rateId}
            label={
              <span>
                Interest rate{" "}
                <span className="text-caption font-normal text-muted">
                  (sample rate, check with your bank)
                </span>
              </span>
            }
            value={ratePercent}
            onValueChange={(val) => {
              isTouchedRef.current = true;
              setRatePercent(val);
            }}
            decimals={2}
            suffix="%"
            error={rateError}
            hint="Sample rate between 6.00% and 15.00% in 0.05% steps (defaults to 8.50%)"
          />
        </div>

        {/* Calculation Output (no aria-live on the whole block, Should 9) */}
        <div
          data-testid="emi-output"
          className="flex flex-col justify-between gap-5 rounded-card border border-gold-line-strong bg-noir-900 p-5 md:p-6"
        >
          {emiResult ? (
            <div className="flex flex-col gap-4">
              <span className="text-caption font-bold uppercase tracking-[0.08em] text-gold-400">
                MONTHLY EMI
              </span>
              <strong
                data-testid="emi-monthly-result"
                className="font-display text-[clamp(28px,5vw,40px)] leading-none font-semibold text-gold-300 tabular-nums"
              >
                {formatInrFull(emiResult.monthlyEmi)}
              </strong>

              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 border-t border-gold-line/40 pt-4 text-small">
                <dt className="text-muted">Loan</dt>
                <dd className="text-right font-semibold text-body tabular-nums">
                  {formatInrFull(emiResult.totalPaid - emiResult.totalInterest)}
                </dd>

                <dt className="text-muted">Total interest</dt>
                <dd className="text-right font-semibold text-body tabular-nums">
                  {formatInrFull(emiResult.totalInterest)}
                </dd>

                <dt className="text-muted">Total paid</dt>
                <dd className="text-right font-semibold text-body tabular-nums">
                  {formatInrFull(emiResult.totalPaid)}
                </dd>

                <dt className="text-muted">Over</dt>
                <dd className="text-right font-semibold text-body" data-testid="emi-over-duration">
                  {emiResult.years} years ({emiResult.months} months)
                </dd>
              </dl>
            </div>
          ) : (
            <div className="flex flex-col gap-2 py-4">
              <span className="text-caption font-bold uppercase tracking-[0.08em] text-gold-400">
                MONTHLY EMI
              </span>
              <p className="text-body text-muted">
                {loanAmount && loanAmount > 0 && ratePercent === null
                  ? "Enter an interest rate"
                  : priceOnRequest
                    ? "Enter a loan amount to see the estimated EMI breakdown."
                    : "Type a loan amount above to calculate your estimated monthly EMI."}
              </p>
            </div>
          )}

          <p className="border-t border-gold-line/30 pt-3 text-caption text-muted">
            Indicative only, not a loan offer. Your bank decides the amount, rate and tenure.
          </p>
        </div>
      </div>
    </section>
  );
}
