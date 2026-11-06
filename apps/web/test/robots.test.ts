/**
 * Unit tests for robots.txt generator (task 5.6b).
 *
 * Verifies:
 *   - Default (no ALLOW_INDEXING or not "true") -> Disallow: /, plus Sitemap: <SITE_URL>/sitemap.xml.
 *   - ALLOW_INDEXING=true with APP_ENV=production -> Allow: /, Disallow: ["/admin", "/api"].
 *   - ALLOW_INDEXING=true with APP_ENV=staging -> still blocked (Disallow: /).
 *   - ALLOW_INDEXING=true with APP_ENV=development -> still blocked (Disallow: /).
 *   - The Sitemap line is always present.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import robots from "../src/app/robots";

describe("robots (Task 5.6b)", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv, SITE_URL: "https://empirebuildcon.com" };
    delete process.env.ALLOW_INDEXING;
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it("blocks all crawlers by default and includes the sitemap URL", () => {
    process.env.APP_ENV = "production";
    delete process.env.ALLOW_INDEXING;

    const result = robots();

    expect(result.rules).toEqual([{ userAgent: "*", disallow: "/" }]);
    expect(result.sitemap).toBe("https://empirebuildcon.com/sitemap.xml");
  });

  it("allows crawling with /admin and /api disallowed when ALLOW_INDEXING=true and APP_ENV=production", () => {
    process.env.APP_ENV = "production";
    process.env.ALLOW_INDEXING = "true";

    const result = robots();

    expect(result.rules).toEqual([{ userAgent: "*", allow: "/", disallow: ["/admin", "/api"] }]);
    expect(result.sitemap).toBe("https://empirebuildcon.com/sitemap.xml");
  });

  it("remains blocked when ALLOW_INDEXING=true but APP_ENV=staging", () => {
    process.env.APP_ENV = "staging";
    process.env.ALLOW_INDEXING = "true";

    const result = robots();

    expect(result.rules).toEqual([{ userAgent: "*", disallow: "/" }]);
    expect(result.sitemap).toBe("https://empirebuildcon.com/sitemap.xml");
  });

  it("remains blocked when ALLOW_INDEXING=true but APP_ENV=development", () => {
    process.env.APP_ENV = "development";
    process.env.ALLOW_INDEXING = "true";

    const result = robots();

    expect(result.rules).toEqual([{ userAgent: "*", disallow: "/" }]);
    expect(result.sitemap).toBe("https://empirebuildcon.com/sitemap.xml");
  });

  it("always includes the sitemap directive regardless of indexing toggle", () => {
    // Unset ALLOW_INDEXING
    delete process.env.ALLOW_INDEXING;
    expect(robots().sitemap).toBe("https://empirebuildcon.com/sitemap.xml");

    // Blocked staging
    process.env.APP_ENV = "staging";
    process.env.ALLOW_INDEXING = "true";
    expect(robots().sitemap).toBe("https://empirebuildcon.com/sitemap.xml");

    // Allowed production
    process.env.APP_ENV = "production";
    process.env.ALLOW_INDEXING = "true";
    expect(robots().sitemap).toBe("https://empirebuildcon.com/sitemap.xml");
  });
});
