// Unit tests for the phone and India-time helpers used by the lead screens (CODE_STYLE §5).
import { describe, expect, it } from "vitest";
import {
  addDays,
  formatAge,
  formatClock,
  formatPhone,
  isCalendarDate,
  isIndianMobile,
  istDate,
  istTime,
  istToIso,
  maskPhone,
  startOfWeek,
  telHref,
  weekdayIndex,
  whatsappHref,
} from "../src/format";

describe("maskPhone", () => {
  it.each([
    ["+919876543210", "+91 98xxxxxx10"],
    ["+916000000001", "+91 60xxxxxx01"],
    ["+911204567890", "+91 12xxxxxx90"],
  ])("masks %s as %s", (e164, masked) => {
    expect(maskPhone(e164)).toBe(masked);
  });

  it("never shows more than four leading and two trailing characters of other numbers", () => {
    expect(maskPhone("+971501234112")).toBe("+971xxxxxxx12");
  });

  it("leaves an erased stub alone", () => {
    expect(maskPhone("[erased]")).toBe("[erased]");
  });
});

describe("formatPhone and links", () => {
  it("shows the full Indian number five and five", () => {
    expect(formatPhone("+919876543210")).toBe("+91 98765 43210");
    expect(formatPhone("[erased]")).toBe("[erased]");
  });

  it("builds tap-to-call for any number and WhatsApp only for mobiles", () => {
    expect(telHref("+919876543210")).toBe("tel:+919876543210");
    expect(whatsappHref("+919876543210")).toBe("https://wa.me/919876543210");
    // A Noida landline (STD 120) can be called but not reached on WhatsApp.
    expect(isIndianMobile("+911204567890")).toBe(false);
    expect(telHref("+911204567890")).toBe("tel:+911204567890");
    expect(whatsappHref("+911204567890")).toBeNull();
    expect(telHref("[erased]")).toBeNull();
    expect(whatsappHref("[erased]")).toBeNull();
  });
});

describe("India time", () => {
  it("puts an instant on its Indian calendar day", () => {
    // 18:29 UTC is 23:59 in India; 18:30 UTC is already the next day.
    expect(istDate("2026-10-24T18:29:00Z")).toBe("2026-10-24");
    expect(istDate("2026-10-24T18:30:00Z")).toBe("2026-10-25");
    expect(istTime("2026-10-24T05:30:00Z")).toBe("11:00");
  });

  it("turns a date and time typed in India into UTC", () => {
    expect(istToIso("2026-10-24", "11:00")).toBe("2026-10-24T05:30:00.000Z");
    expect(istToIso("2026-10-25", "00:15")).toBe("2026-10-24T18:45:00.000Z");
  });

  it("refuses half-typed or impossible dates and times", () => {
    expect(() => istToIso("2026-02-31", "11:00")).toThrow(RangeError);
    expect(() => istToIso("2026-10-24", "25:00")).toThrow(RangeError);
    expect(() => istToIso("24/10/2026", "11:00")).toThrow(RangeError);
    expect(isCalendarDate("2026-10-24")).toBe(true);
    expect(isCalendarDate("2026-13-01")).toBe(false);
  });

  it("counts days and weeks from Monday", () => {
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
    // Sat 24 Oct 2026 belongs to the week starting Mon 19 Oct.
    expect(weekdayIndex("2026-10-24")).toBe(5);
    expect(startOfWeek("2026-10-24")).toBe("2026-10-19");
    expect(startOfWeek("2026-10-19")).toBe("2026-10-19");
    expect(startOfWeek("2026-10-25")).toBe("2026-10-19");
  });

  it("formats clock times the board's way", () => {
    expect(formatClock("00:05")).toBe("12:05 am");
    expect(formatClock("11:00")).toBe("11:00 am");
    expect(formatClock("12:30")).toBe("12:30 pm");
    expect(formatClock("18:00")).toBe("6:00 pm");
  });
});

describe("formatAge", () => {
  const now = new Date("2026-10-23T12:00:00Z");
  it.each([
    ["2026-10-23T12:00:30Z", "just now"],
    ["2026-10-23T11:52:00Z", "8 min"],
    ["2026-10-23T09:00:00Z", "3 h"],
    ["2026-10-21T12:00:00Z", "2 d"],
    ["2026-09-18T12:00:00Z", "5 wk"],
    ["2026-06-23T12:00:00Z", "4 mo"],
    ["2024-10-01T12:00:00Z", "2 yr"],
    ["2026-10-23T12:05:00Z", "just now"],
  ])("%s is %s old", (instant, age) => {
    expect(formatAge(instant, now)).toBe(age);
  });
});
