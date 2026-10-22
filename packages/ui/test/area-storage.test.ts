// Storage precision for area (handbook/ARCHITECTURE.md §6: area is stored once, in square metres).
// Kept apart from format.test.ts, whose vectors the API's Python twin copies.
import { describe, expect, it } from "vitest";
import { sqftToSqmStored, sqmToSqft } from "../src/format";

describe("sqftToSqmStored", () => {
  it("keeps four decimals", () => {
    expect(sqftToSqmStored(980)).toBe(91.0449);
    expect(sqftToSqmStored(720)).toBe(66.8902);
  });

  it("round-trips every whole square-foot value back to itself", () => {
    for (let sqft = 0; sqft <= 50_000; sqft += 1) {
      expect(sqmToSqft(sqftToSqmStored(sqft))).toBe(sqft);
    }
  });
});
