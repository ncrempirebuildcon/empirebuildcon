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
 *   - Outputs:
 *       Monthly EMI, total interest, total paid, and number of months.
 *       Reducing-balance formula: EMI = P · r · (1+r)^n / ((1+r)^n − 1), with 0% giving P/n.
 *       Amounts formatted in ₹ with Indian grouping, rounded to whole rupees.
 *   - Honesty:
 *       - Rate field says "Sample rate, check with your bank".
 *       - Note: "Indicative only, not a loan offer. Your bank decides the amount, rate and tenure."
 *       - No bank names, no fake urgency or lowest-EMI claims.
 *   - Without JavaScript: renders the formula and note instead.
 */
import { useId, useState, useSyncExternalStore } from "react";
import { NumberField } from "@empire/ui";
import { Select } from "@empire/ui";
import { formatInrFull } from "@empire/ui";
import {
  calculateEmi,
  clampRate,
  clampTenureYears,
  EMI_LIMITS,
  isRateValid,
  isTenureYearsValid,
  type EmiResult,
} from "@/lib/tools/emi";

export interface EmiCalculatorProps {
  /** Pre-filled price in whole rupees, or null/undefined when on request. */
  defaultPriceInr?: number | null;
  /** Whether the price is on request. */
  priceOnRequest?: boolean;
}

function noopSubscribe() {
  return () => {};
}

function getClientMounted() {
  return true;
}

function getServerMounted() {
  return false;
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
  const isMounted = useSyncExternalStore(noopSubscribe, getClientMounted, getServerMounted);

  const initialPrincipal =
    !priceOnRequest && defaultPriceInr && defaultPriceInr > 0 ? Math.round(defaultPriceInr) : null;

  const [loanAmount, setLoanAmount] = useState<number | null>(initialPrincipal);
  const [tenureYears, setTenureYears] = useState<number>(EMI_LIMITS.DEFAULT_TENURE_YEARS);
  const [ratePercent, setRatePercent] = useState<number>(EMI_LIMITS.DEFAULT_RATE);

  const tenureId = useId();
  const rateId = useId();
  const loanId = useId();

  if (!isMounted) {
    // Progressive enhancement: when JavaScript is disabled, render formula and note instead
    return (
      <section id="emi" aria-labelledby="emi-heading" className="flex flex-col gap-6">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2
            id="emi-heading"
            className="font-display text-[clamp(24px,4vw,34px)] leading-tight font-semibold text-metallic"
          >
            EMI calculator
          </h2>
          <span className="text-caption font-semibold text-gold-400 uppercase tracking-[0.08em]">
            Sample rates · check with your bank
          </span>
        </div>

        <div
          className="rounded-card border border-gold-line bg-noir-800 p-6 flex flex-col gap-3 text-body"
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
          <p className="text-caption text-muted border-t border-gold-line/30 pt-3">
            Sample rates, check with your bank. Indicative only, not a loan offer. Your bank decides
            the amount, rate and tenure.
          </p>
        </div>
      </section>
    );
  }

  let emiResult: EmiResult | null = null;
  let calculationError: string | null = null;

  if (loanAmount !== null && loanAmount > 0) {
    try {
      const validTenure = isTenureYearsValid(tenureYears)
        ? tenureYears
        : clampTenureYears(tenureYears);
      const validRate = isRateValid(ratePercent) ? ratePercent : clampRate(ratePercent);
      emiResult = calculateEmi({
        principal: loanAmount,
        annualRatePercent: validRate,
        tenureYears: validTenure,
      });
    } catch (err) {
      calculationError = err instanceof Error ? err.message : "Calculation error";
    }
  }

  return (
    <section id="emi" aria-labelledby="emi-heading" className="flex flex-col gap-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2
          id="emi-heading"
          className="font-display text-[clamp(24px,4vw,34px)] leading-tight font-semibold text-metallic"
        >
          EMI calculator
        </h2>
        <span className="text-caption font-semibold text-gold-400 uppercase tracking-[0.08em]">
          Sample rates · check with your bank
        </span>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.3fr_1fr]">
        {/* Form controls */}
        <div className="flex flex-col gap-5 rounded-card border border-line bg-noir-800 p-5 md:p-6">
          <NumberField
            id={loanId}
            label="Loan amount"
            value={loanAmount}
            onValueChange={setLoanAmount}
            prefix={priceOnRequest && (!loanAmount || loanAmount <= 0) ? undefined : "₹"}
            hint={
              priceOnRequest && (loanAmount === null || loanAmount <= 0)
                ? "Enter a loan amount to calculate estimated EMI"
                : "Whole rupees with Indian digit grouping"
            }
          />

          <Select
            id={tenureId}
            label="Tenure"
            value={String(tenureYears)}
            options={TENURE_OPTIONS}
            onChange={(e) => {
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
              if (val !== null) setRatePercent(val);
            }}
            decimals={2}
            suffix="%"
            hint="Sample rate between 6.00% and 15.00% (defaults to 8.50%)"
          />
        </div>

        {/* Calculation Output */}
        <div
          aria-live="polite"
          className="flex flex-col justify-between gap-5 rounded-card border border-gold-line-strong bg-noir-900 p-5 md:p-6"
        >
          {emiResult ? (
            <div className="flex flex-col gap-4">
              <span className="text-caption font-bold tracking-[0.08em] text-gold-400 uppercase">
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
              <span className="text-caption font-bold tracking-[0.08em] text-gold-400 uppercase">
                MONTHLY EMI
              </span>
              <p className="text-body text-muted">
                {priceOnRequest
                  ? "Enter a loan amount to see the estimated EMI breakdown."
                  : "Type a loan amount above to calculate your estimated monthly EMI."}
              </p>
              {calculationError ? (
                <p className="text-small text-danger">{calculationError}</p>
              ) : null}
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
