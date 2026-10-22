// Unit tests for the money and area display helpers (handbook/CODE_STYLE.md §5).
import { describe, expect, it } from "vitest";
import {
  formatArea,
  formatAreaRange,
  formatInr,
  formatInrFull,
  formatInrRange,
  sqftToSqm,
  sqmToSqft,
} from "../src/format";

describe("formatInr", () => {
  it.each([
    [0, "₹ 0"],
    [99_999, "₹ 99,999"],
    [1_00_000, "₹ 1 L"],
    [78_00_000, "₹ 78 L"],
    [86_00_000, "₹ 86 L"],
    [12_34_567, "₹ 12.35 L"],
    [1_08_00_000, "₹ 1.08 Cr"],
    [1_25_00_000, "₹ 1.25 Cr"],
    [2_40_00_000, "₹ 2.4 Cr"],
    [99_99_999, "₹ 1 Cr"],
  ])("formats %d as %s", (amount, expected) => {
    expect(formatInr(amount)).toBe(expected);
  });

  it("rejects negative and non-finite amounts", () => {
    expect(() => formatInr(-1)).toThrow(RangeError);
    expect(() => formatInr(Number.NaN)).toThrow(RangeError);
  });

  it("formats full figures with Indian grouping", () => {
    expect(formatInrFull(12_34_567)).toBe("₹ 12,34,567");
  });

  it("formats ranges and collapses equal ends", () => {
    expect(formatInrRange(78_00_000, 1_25_00_000)).toBe("₹ 78 L – ₹ 1.25 Cr");
    expect(formatInrRange(2_10_00_000, 2_10_00_000)).toBe("₹ 2.1 Cr");
    expect(() => formatInrRange(2, 1)).toThrow(RangeError);
  });
});

describe("area", () => {
  it.each([
    [720, 66.9],
    [780, 72.5],
    [980, 91.0],
    [1120, 104.1],
  ])("converts %d sq ft to %d sq m", (sqft, sqm) => {
    expect(sqftToSqm(sqft)).toBe(sqm);
  });

  it("converts square metres back to whole square feet", () => {
    expect(sqmToSqft(91.04)).toBe(980);
  });

  it("formats carpet area in both units", () => {
    expect(formatArea(980)).toBe("980 sq ft · 91.0 sq m");
    expect(formatArea(1120)).toBe("1,120 sq ft · 104.1 sq m");
    expect(formatArea(91.04, "sqm")).toBe("980 sq ft · 91.0 sq m");
  });

  it("formats area ranges", () => {
    expect(formatAreaRange(720, 1120)).toBe("720 – 1,120 sq ft · 66.9 – 104.1 sq m");
    expect(formatAreaRange(980, 980)).toBe("980 sq ft · 91.0 sq m");
  });
});
