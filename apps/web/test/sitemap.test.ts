/**
 * Unit tests for sitemap.xml generator (task 5.6b).
 *
 * Verifies:
 *   - Entries from mocked API response become absolute SITE_URL URLs with lastModified.
 *   - List pages (/, /projects, /properties, /contact, /blog) are present once (no duplicates).
 *   - List pages without API lastmod have no lastModified.
 *   - When API returns lastmod for a list page, its lastModified is preserved.
 *   - No priority or changeFrequency are present.
 *   - Throws when API call fails.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import sitemap, { LIST_PAGE_PATHS } from "../src/app/sitemap";
import * as api from "../src/lib/public/api";

describe("sitemap (Task 5.6b)", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv, SITE_URL: "https://empirebuildcon.com" };
    vi.restoreAllMocks();
  });

  afterEach(() => {
    process.env = originalEnv;
    vi.restoreAllMocks();
  });

  it("converts API entries into absolute SITE_URL URLs with lastModified", async () => {
    vi.spyOn(api, "fetchPublicSitemap").mockResolvedValueOnce([
      {
        path: "/",
        lastmod: "2026-11-04T12:00:00Z",
        alternates: {},
      },
      {
        path: "/projects/noida-heights",
        lastmod: "2026-11-02T15:30:00Z",
        alternates: {},
      },
      {
        path: "/projects/noida-heights/3bhk",
        lastmod: "2026-11-02T16:00:00Z",
        alternates: {},
      },
      {
        path: "/cities/noida",
        lastmod: "2026-11-02T15:30:00Z",
        alternates: {},
      },
      {
        path: "/blog",
        lastmod: "2026-11-03T10:00:00Z",
        alternates: {},
      },
      {
        path: "/blog/first-post",
        lastmod: "2026-11-03T11:00:00Z",
        alternates: {},
      },
    ]);

    const result = await sitemap();

    // Verify all URLs start with SITE_URL
    for (const item of result) {
      expect(item.url).toMatch(/^https:\/\/empirebuildcon\.com/);
    }

    // Check specific API project entry
    const projectEntry = result.find(
      (item) => item.url === "https://empirebuildcon.com/projects/noida-heights",
    );
    expect(projectEntry).toBeDefined();
    expect(projectEntry?.lastModified).toEqual(new Date("2026-11-02T15:30:00Z"));

    // Check configuration entry
    const configEntry = result.find(
      (item) => item.url === "https://empirebuildcon.com/projects/noida-heights/3bhk",
    );
    expect(configEntry).toBeDefined();
    expect(configEntry?.lastModified).toEqual(new Date("2026-11-02T16:00:00Z"));

    // Check city entry
    const cityEntry = result.find((item) => item.url === "https://empirebuildcon.com/cities/noida");
    expect(cityEntry).toBeDefined();
    expect(cityEntry?.lastModified).toEqual(new Date("2026-11-02T15:30:00Z"));

    // Check blog post entry
    const postEntry = result.find(
      (item) => item.url === "https://empirebuildcon.com/blog/first-post",
    );
    expect(postEntry).toBeDefined();
    expect(postEntry?.lastModified).toEqual(new Date("2026-11-03T11:00:00Z"));

    // Verify no priority or changeFrequency are present on any entry
    for (const item of result) {
      expect(item).not.toHaveProperty("priority");
      expect(item).not.toHaveProperty("changeFrequency");
    }
  });

  it("ensures core list pages are present exactly once without duplicates", async () => {
    // API returns / and /blog and an extra page, but omits /projects, /properties, /contact
    vi.spyOn(api, "fetchPublicSitemap").mockResolvedValueOnce([
      { path: "/", lastmod: "2026-11-04T12:00:00Z", alternates: {} },
      { path: "/blog", lastmod: "2026-11-03T10:00:00Z", alternates: {} },
      { path: "/about", lastmod: "2026-11-01T08:00:00Z", alternates: {} },
    ]);

    const result = await sitemap();

    // Verify each required list page exists exactly once
    for (const requiredPath of LIST_PAGE_PATHS) {
      const expectedUrl = `https://empirebuildcon.com${requiredPath === "/" ? "/" : requiredPath}`;
      const matching = result.filter((item) => item.url === expectedUrl);
      expect(matching, `Path ${requiredPath} should appear exactly once`).toHaveLength(1);
    }

    // For list pages not provided with a lastmod by the API, lastModified is undefined
    const projectsEntry = result.find((item) => item.url === "https://empirebuildcon.com/projects");
    expect(projectsEntry).toBeDefined();
    expect(projectsEntry?.lastModified).toBeUndefined();

    const propertiesEntry = result.find(
      (item) => item.url === "https://empirebuildcon.com/properties",
    );
    expect(propertiesEntry).toBeDefined();
    expect(propertiesEntry?.lastModified).toBeUndefined();

    const contactEntry = result.find((item) => item.url === "https://empirebuildcon.com/contact");
    expect(contactEntry).toBeDefined();
    expect(contactEntry?.lastModified).toBeUndefined();

    // List pages that were in the API keep their lastModified
    const homeEntry = result.find((item) => item.url === "https://empirebuildcon.com/");
    expect(homeEntry).toBeDefined();
    expect(homeEntry?.lastModified).toEqual(new Date("2026-11-04T12:00:00Z"));

    const blogEntry = result.find((item) => item.url === "https://empirebuildcon.com/blog");
    expect(blogEntry).toBeDefined();
    expect(blogEntry?.lastModified).toEqual(new Date("2026-11-03T10:00:00Z"));
  });

  it("deduplicates when the API also explicitly returns /projects and /contact", async () => {
    vi.spyOn(api, "fetchPublicSitemap").mockResolvedValueOnce([
      { path: "/", lastmod: "2026-11-04T12:00:00Z", alternates: {} },
      { path: "/projects", lastmod: "2026-11-04T14:00:00Z", alternates: {} },
      { path: "/contact", lastmod: "2026-11-04T15:00:00Z", alternates: {} },
    ]);

    const result = await sitemap();

    const projectsEntries = result.filter(
      (item) => item.url === "https://empirebuildcon.com/projects",
    );
    expect(projectsEntries).toHaveLength(1);
    expect(projectsEntries[0]?.lastModified).toEqual(new Date("2026-11-04T14:00:00Z"));

    const contactEntries = result.filter(
      (item) => item.url === "https://empirebuildcon.com/contact",
    );
    expect(contactEntries).toHaveLength(1);
    expect(contactEntries[0]?.lastModified).toEqual(new Date("2026-11-04T15:00:00Z"));
  });

  it("throws when the API call fails rather than returning an empty sitemap", async () => {
    vi.spyOn(api, "fetchPublicSitemap").mockRejectedValueOnce(
      new Error("API connection refused: 500"),
    );

    await expect(sitemap()).rejects.toThrow("API connection refused: 500");
  });
});
