/**
 * robots.txt: blocks all crawlers until go-live (handbook/ARCHITECTURE.md §16, task 5.6b).
 *
 * Default (ships): Disallow: / for every agent, plus Sitemap: <SITE_URL>/sitemap.xml.
 * Go-live switch: ALLOW_INDEXING=true turns it into Allow: / with Disallow: /admin and Disallow: /api.
 * It only works when APP_ENV=production too. Staging and development remain blocked.
 *
 * TODO(phase-9): switch on ALLOW_INDEXING=true in production environment at go-live.
 *
 * Collaborators: Antigravity <noreply@google.com>. Decisions: D-046, D-047.
 */
import type { MetadataRoute } from "next";
import { absoluteUrl } from "@/lib/public/seo";

export default function robots(): MetadataRoute.Robots {
  const allowIndexing =
    process.env.ALLOW_INDEXING === "true" && process.env.APP_ENV === "production";

  return {
    rules: [
      allowIndexing
        ? { userAgent: "*", allow: "/", disallow: ["/admin", "/api"] }
        : { userAgent: "*", disallow: "/" },
    ],
    sitemap: absoluteUrl("/sitemap.xml"),
  };
}
