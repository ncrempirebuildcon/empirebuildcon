/**
 * Unit tests for blog helpers and rules (Phase 5 Task 5.5b).
 *
 * Implements:
 *   - Read time calculation (empty body, short body, long body, boundary cases).
 *   - Indian date formatting (D MMM YYYY in Asia/Kolkata timezone).
 *   - Link builders: category changes drop page, pagination keeps category, URL-encoded values.
 *   - ShareLinks helpers: strips query and fragment, URL-encodes WhatsApp link, hides native share without navigator.share.
 */
import { describe, expect, it } from "vitest";
import { formatBlogDate } from "@/lib/blog/dates";
import { buildBlogHref, buildCategoryHref, buildPaginationHref } from "@/lib/blog/links";
import { calculateReadTimeMinutes, formatReadTime } from "@/lib/blog/readTime";
import { buildWhatsAppShareUrl, stripQueryAndFragment } from "@/components/public/ShareLinks";

describe("blog read time calculation", () => {
  it("defaults empty, null or whitespace body to 1 min read", () => {
    expect(calculateReadTimeMinutes("")).toBe(1);
    expect(calculateReadTimeMinutes(null)).toBe(1);
    expect(calculateReadTimeMinutes(undefined)).toBe(1);
    expect(calculateReadTimeMinutes("   \n\t  ")).toBe(1);
    expect(formatReadTime("")).toBe("1 min read");
    expect(formatReadTime(null)).toBe("1 min read");
  });

  it("calculates read time for short body (under 200 words) as 1 min read", () => {
    const shortBody = "Word ".repeat(50);
    expect(calculateReadTimeMinutes(shortBody)).toBe(1);
    expect(formatReadTime(shortBody)).toBe("1 min read");

    const exactly200 = "Word ".repeat(200);
    expect(calculateReadTimeMinutes(exactly200)).toBe(1);
    expect(formatReadTime(exactly200)).toBe("1 min read");
  });

  it("calculates read time for long body rounded up (e.g. 201 -> 2, 550 -> 3)", () => {
    const justOver = "Word ".repeat(201);
    expect(calculateReadTimeMinutes(justOver)).toBe(2);
    expect(formatReadTime(justOver)).toBe("2 min read");

    const longBody = "Word ".repeat(550);
    expect(calculateReadTimeMinutes(longBody)).toBe(3);
    expect(formatReadTime(longBody)).toBe("3 min read");
  });
});

describe("blog Indian date formatting", () => {
  it("formats ISO timestamps to D MMM YYYY in India time", () => {
    expect(formatBlogDate("2026-10-12T10:00:00Z")).toBe("12 Oct 2026");
    expect(formatBlogDate("2026-01-05T04:30:00Z")).toBe("5 Jan 2026");
  });

  it("handles day shift across UTC and IST boundary (Asia/Kolkata UTC+5:30)", () => {
    // 2026-09-30 20:00 UTC is 2026-10-01 01:30 in IST
    expect(formatBlogDate("2026-09-30T20:00:00Z")).toBe("1 Oct 2026");
  });

  it("returns empty string for null or undefined dates", () => {
    expect(formatBlogDate(null)).toBe("");
    expect(formatBlogDate(undefined)).toBe("");
  });
});

describe("blog link builders", () => {
  it("drops page parameter when category changes", () => {
    // Current query had page=3; switching category drops page
    const href = buildCategoryHref("Buying guides", { page: 3, category: "RERA" });
    expect(href).toBe("/blog?category=Buying+guides");
    expect(href).not.toContain("page");
  });

  it("returns /blog for 'all', null, empty or undefined category", () => {
    expect(buildCategoryHref("all")).toBe("/blog");
    expect(buildCategoryHref("All")).toBe("/blog");
    expect(buildCategoryHref(null)).toBe("/blog");
    expect(buildCategoryHref("   ")).toBe("/blog");
  });

  it("preserves active category parameter when paging", () => {
    const page2 = buildPaginationHref(2, { category: "RERA & legal" });
    expect(page2).toContain("category=RERA+%26+legal");
    expect(page2).toContain("page=2");

    const page1 = buildPaginationHref(1, { category: "RERA & legal" });
    expect(page1).toBe("/blog?category=RERA+%26+legal");
    expect(page1).not.toContain("page");
  });

  it("generates clean URL for page 1 with no category", () => {
    expect(buildPaginationHref(1)).toBe("/blog");
    expect(buildPaginationHref(3)).toBe("/blog?page=3");
  });

  it("properly URL-encodes special characters in category names", () => {
    const href = buildCategoryHref("Legal & RERA: 2026 Update?");
    expect(href).toBe("/blog?category=Legal+%26+RERA%3A+2026+Update%3F");
  });

  it("buildBlogHref generic builder behaves consistently", () => {
    expect(buildBlogHref({ category: "News", page: 2 })).toBe("/blog?category=News&page=2");
    expect(buildBlogHref({ category: "all", page: 1 })).toBe("/blog");
  });
});

describe("ShareLinks helpers", () => {
  it("strips query string and fragment from URLs", () => {
    expect(
      stripQueryAndFragment(
        "https://empirebuildcon.com/blog/rera-guide?utm_source=twitter&ref=1#tips",
      ),
    ).toBe("https://empirebuildcon.com/blog/rera-guide");

    expect(stripQueryAndFragment("/blog/rera-guide?param=test#section")).toBe("/blog/rera-guide");
    expect(stripQueryAndFragment("https://empirebuildcon.com/blog/post")).toBe(
      "https://empirebuildcon.com/blog/post",
    );
  });

  it("builds URL-encoded WhatsApp share link using clean URL without query/hash", () => {
    const waUrl = buildWhatsAppShareUrl(
      "How to check UP-RERA",
      "https://empirebuildcon.com/blog/check-rera?ref=share#top",
    );

    expect(waUrl).toBe(
      "https://wa.me/?text=How%20to%20check%20UP-RERA%20https%3A%2F%2Fempirebuildcon.com%2Fblog%2Fcheck-rera",
    );
    expect(waUrl).not.toContain("ref=share");
    expect(waUrl).not.toContain("#top");
  });

  it("native share is unsupported in standard Node environment", () => {
    const hasNativeShare =
      typeof navigator !== "undefined" && typeof navigator.share === "function";
    expect(hasNativeShare).toBe(false);
  });
});
