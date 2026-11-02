import { describe, expect, it } from "vitest";
import {
  buildTelLink,
  buildWhatsAppLink,
  filterPlaceholders,
  filterValue,
  formatWhatsAppDigits,
  isPlaceholder,
} from "../src/lib/public/format";

describe("public format and placeholder helpers", () => {
  it("detects bracketed placeholders", () => {
    expect(isPlaceholder("[Phone number]")).toBe(true);
    expect(isPlaceholder("[sales@empirebuildcon.com]")).toBe(true);
    expect(isPlaceholder("[Office address, city, PIN]")).toBe(true);
    expect(isPlaceholder("+91 98765 43210")).toBe(false);
    expect(isPlaceholder("")).toBe(true);
    expect(isPlaceholder(null)).toBe(true);
  });

  it("formats WhatsApp digits properly", () => {
    expect(formatWhatsAppDigits("+91 98765-43210")).toBe("919876543210");
    expect(formatWhatsAppDigits("011 2345 6789")).toBe("01123456789");
  });

  it("builds WhatsApp link with {page} replaced and digits formatted", () => {
    const link = buildWhatsAppLink(
      "+91 98765 43210",
      "Hello Empire, I am viewing {page}",
      "/projects/aurum-heights",
      false,
    );
    expect(link).toBe(
      "https://wa.me/919876543210?text=Hello%20Empire%2C%20I%20am%20viewing%20%2Fprojects%2Faurum-heights",
    );
  });

  it("replaces multiple occurrences of {page}", () => {
    const link = buildWhatsAppLink(
      "+91 98765 43210",
      "Page: {page}. Question about {page}.",
      "/contact",
      false,
    );
    expect(link).toBe(
      "https://wa.me/919876543210?text=Page%3A%20%2Fcontact.%20Question%20about%20%2Fcontact.",
    );
  });

  it("builds tel link stripping formatting characters", () => {
    expect(buildTelLink("+91 (120) 456-7890", false)).toBe("tel:+911204567890");
    expect(buildTelLink("9876543210", false)).toBe("tel:9876543210");
  });

  it("hides placeholders in production mode", () => {
    const isProduction = true;
    expect(buildWhatsAppLink("[Phone number]", "Hello", "/home", isProduction)).toBeNull();
    expect(buildTelLink("[Phone number]", isProduction)).toBeNull();
    expect(filterValue("[Office address]", isProduction)).toBeNull();

    const phones = filterPlaceholders(
      ["+91 98765 43210", "[Secondary phone]", "   ", null],
      isProduction,
    );
    expect(phones).toEqual(["+91 98765 43210"]);

    const emails = filterPlaceholders(
      ["[sales@empirebuildcon.com]", "info@empirebuildcon.com"],
      isProduction,
    );
    expect(emails).toEqual(["info@empirebuildcon.com"]);
  });

  it("keeps placeholders in non-production mode for development review", () => {
    const isProduction = false;
    expect(buildWhatsAppLink("+91 98765 43210", "Hello", "/home", isProduction)).not.toBeNull();
    expect(filterValue("[Office address]", isProduction)).toBe("[Office address]");

    const phones = filterPlaceholders(["+91 98765 43210", "[Secondary phone]"], isProduction);
    expect(phones).toEqual(["+91 98765 43210", "[Secondary phone]"]);
  });
});
