/**
 * sitemap.xml: lists every public page from the API plus core list pages (task 5.6b, D-046).
 *
 * Implements ARCHITECTURE §16 (SEO):
 *   - Source: GET /api/v1/public/sitemap through the public data layer (fetchPublicSitemap)
 *     with cache tag 'sitemap' and revalidation, never at build time only.
 *   - Canonical URLs on SITE_URL via absoluteUrl(), never another host.
 *   - lastModified derived from API lastmod.
 *   - No priority or changefreq (Google ignores them, and we don't invent values).
 *   - List pages: /, /projects, /properties, /contact, and /blog are present exactly once,
 *     even if the API leaves them out (with no lastModified then).
 *   - When the API fails, the route answers with an error, not an empty sitemap.
 *
 * Collaborators: Antigravity <noreply@google.com>. Decisions: D-046, D-047.
 */
import type { MetadataRoute } from "next";
import { fetchPublicSitemap } from "@/lib/public/api";
import { absoluteUrl } from "@/lib/public/seo";

export const dynamic = "force-dynamic";

/** Core list pages that must always appear in the sitemap. */
export const LIST_PAGE_PATHS = ["/", "/projects", "/properties", "/contact", "/blog"] as const;

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const entries = await fetchPublicSitemap();

  // Deduplicate and merge: Map preserves insertion order.
  // 1. Seed the core list pages first (without lastModified).
  const pageMap = new Map<string, { path: string; lastModified?: Date }>();
  for (const path of LIST_PAGE_PATHS) {
    pageMap.set(path, { path });
  }

  // 2. Overlay API entries (updating lastModified for list pages if present,
  //    and appending all other public pages).
  for (const entry of entries) {
    if (!entry.path) continue;
    let lastModified: Date | undefined;
    if (entry.lastmod) {
      const parsed = new Date(entry.lastmod);
      if (!Number.isNaN(parsed.getTime())) {
        lastModified = parsed;
      }
    }
    pageMap.set(entry.path, {
      path: entry.path,
      ...(lastModified ? { lastModified } : {}),
    });
  }

  // 3. Build MetadataRoute.Sitemap entries with absolute URLs on SITE_URL.
  return Array.from(pageMap.values()).map((item) => ({
    url: absoluteUrl(item.path),
    ...(item.lastModified ? { lastModified: item.lastModified } : {}),
  }));
}
