/**
 * robots.txt: blocks all crawlers until go-live.
 * TODO(phase-9): allow crawling and add the sitemap URL at the go-live gate (handbook/ARCHITECTURE.md §16).
 */
import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return { rules: [{ userAgent: "*", disallow: "/" }] };
}
