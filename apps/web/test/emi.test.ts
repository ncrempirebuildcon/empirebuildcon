/**
 * Unit tests for EMI calculation (handbook/tasks/phase-5/5.7b-tools.md).
 *
 * Verifies:
 * - known values: ₹ 50,00,000 at 8.5% for 20 years ≈ ₹ 43,391 a month (verified against
 *   SBI and HDFC Bank Home Loan EMI calculators: P=50,00,000, r=8.5%, n=240 => 43,391.16).
 * - 0% interest rate => P / n.
 * - 1 month tenure.
 * - proper whole-rupee rounding.
 * - refusal of inputs outside valid limits (throws RangeError / TypeError).
 */
import { describe, expect, it } from "vitest";
import { calculateEmi, isRateValid, isTenureYearsValid } from "../src/lib/tools/emi";

describe("EMI calculation (Task 5.7b)", () => {
  it("calculates known values: ₹ 50,00,000 at 8.5% for 20 years ≈ ₹ 43,391/month", () => {
    const res = calculateEmi({
      principal: 50_00_000,
      annualRatePercent: 8.5,
      tenureYears: 20,
    });

    expect(res.months).toBe(240);
    expect(res.years).toBe(20);
    expect(res.monthlyEmi).toBe(43391);
    expect(res.totalPaid).toBe(43391 * 240); // 1,04,13,840
    expect(res.totalInterest).toBe(43391 * 240 - 50_00_000); // 54,13,840
    expect(res.rawMonthlyEmi).toBeCloseTo(43391.16, 2);
  });

  it("handles 0% interest rate as pure principal division (P / n)", () => {
    const res = calculateEmi({
      principal: 60_00_000,
      annualRatePercent: 0,
      tenureYears: 5,
    });

    expect(res.months).toBe(60);
    expect(res.monthlyEmi).toBe(1_00_000);
    expect(res.totalInterest).toBe(0);
    expect(res.totalPaid).toBe(60_00_000);
  });

  it("calculates 1 month tenure correctly", () => {
    // ₹ 1,20,000 at 12% annual (1% monthly) for 1 month:
    // EMI = 1,20,000 + 1% = 1,21,200
    const res = calculateEmi({
      principal: 1_20_000,
      annualRatePercent: 12,
      tenureMonths: 1,
    });

    expect(res.months).toBe(1);
    expect(res.monthlyEmi).toBe(121200);
    expect(res.totalInterest).toBe(1200);
    expect(res.totalPaid).toBe(121200);
  });

  it("rounds monthly EMI to nearest whole rupee", () => {
    // P = 10,00,000, r = 9.0%, n = 15 yrs (180 months)
    // raw = 10142.665... => rounds up to 10143
    const res = calculateEmi({
      principal: 10_00_000,
      annualRatePercent: 9.0,
      tenureYears: 15,
    });

    expect(res.rawMonthlyEmi).toBeGreaterThan(10142.5);
    expect(res.rawMonthlyEmi).toBeLessThan(10143.0);
    expect(res.monthlyEmi).toBe(10143);
  });

  it("refuses inputs outside valid limits", () => {
    // Non-positive or non-finite principal
    expect(() => calculateEmi({ principal: 0, annualRatePercent: 8.5, tenureYears: 20 })).toThrow(
      RangeError,
    );
    expect(() =>
      calculateEmi({ principal: -50000, annualRatePercent: 8.5, tenureYears: 20 }),
    ).toThrow(RangeError);
    expect(() =>
      calculateEmi({ principal: 10.5, annualRatePercent: 8.5, tenureYears: 20 }),
    ).toThrow(RangeError);
    expect(() =>
      calculateEmi({ principal: 101_00_00_000, annualRatePercent: 8.5, tenureYears: 20 }),
    ).toThrow(RangeError);

    // Invalid interest rate
    expect(() =>
      calculateEmi({ principal: 50_00_000, annualRatePercent: -1, tenureYears: 20 }),
    ).toThrow(RangeError);
    expect(() =>
      calculateEmi({ principal: 50_00_000, annualRatePercent: 101, tenureYears: 20 }),
    ).toThrow(RangeError);

    // Invalid tenure
    expect(() =>
      calculateEmi({ principal: 50_00_000, annualRatePercent: 8.5, tenureMonths: 0 }),
    ).toThrow(RangeError);
    expect(() =>
      calculateEmi({ principal: 50_00_000, annualRatePercent: 8.5, tenureMonths: -5 }),
    ).toThrow(RangeError);
    expect(() =>
      calculateEmi({ principal: 50_00_000, annualRatePercent: 8.5, tenureYears: 0 }),
    ).toThrow(RangeError);

    // Missing tenure
    expect(() => calculateEmi({ principal: 50_00_000, annualRatePercent: 8.5 })).toThrow(TypeError);
  });

  it("validates UI range helpers", () => {
    expect(isTenureYearsValid(5)).toBe(true);
    expect(isTenureYearsValid(20)).toBe(true);
    expect(isTenureYearsValid(30)).toBe(true);
    expect(isTenureYearsValid(4)).toBe(false);
    expect(isTenureYearsValid(31)).toBe(false);

    expect(isRateValid(6.0)).toBe(true);
    expect(isRateValid(8.5)).toBe(true);
    expect(isRateValid(15.0)).toBe(true);
    expect(isRateValid(5.95)).toBe(false);
    expect(isRateValid(15.05)).toBe(false);
  });
});
