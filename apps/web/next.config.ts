/**
 * Next.js configuration for the Empire web app.
 *
 * How it works:
 *   1. Every browser call to /api/* is rewritten to the API host (API_ORIGIN), so the browser only
 *      ever talks to this site: no CORS in production and a first-party session cookie
 *      (handbook/ARCHITECTURE.md §3).
 *   2. Security headers from handbook/SECURITY.md §4 are set on every page.
 *
 * DO NOT CHANGE: `skipTrailingSlashRedirect: true`. Without it Next.js answers
 * /api/v1/admin/projects/ with a 308 before the rewrite, which broke form posts in the previous
 * project (Current Investor). The API itself never redirects either; a CI test checks both.
 */
import type { NextConfig } from "next";

const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";

// SECURITY: handbook/SECURITY.md §4. HSTS has no `preload` until one month after go-live.
const securityHeaders = [
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  // TODO(phase-5): nonce-based Content-Security-Policy set in the Next.js proxy (proxy.ts),
  // report-only on staging for one week first (SECURITY.md §4).
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  // WHY: `next dev` otherwise writes its own apps/web/AGENTS.md when it detects an AI agent.
  // The repo-root AGENTS.md is the one place for AI rules (handbook/CONTRIBUTING.md §11).
  agentRules: false,
  skipTrailingSlashRedirect: true,
  experimental: {
    // WHY: with a proxy (src/proxy.ts) Next.js buffers request bodies and silently cuts them at
    // 10 MB, so a photo near the API's 10 MB cap would arrive truncated instead of getting the
    // API's clear 413. This is the cap plus 64 KB for the multipart fields. Videos and documents
    // never pass here in production: they go straight from the browser to Cloudinary.
    // SECURITY: keep this close to the API's limit; it bounds the memory one request can take.
    proxyClientMaxBodySize: 10 * 1024 * 1024 + 64 * 1024,
  },
  transpilePackages: ["@empire/ui", "@empire/api-client"],
  images: {
    remotePatterns: [{ protocol: "https", hostname: "res.cloudinary.com" }],
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }];
  },
  async headers() {
    return [
      { source: "/:path*", headers: securityHeaders },
      // SECURITY: CMS pages hold personal data (leads); never cache them anywhere.
      { source: "/admin/:path*", headers: [{ key: "Cache-Control", value: "no-store" }] },
      { source: "/admin", headers: [{ key: "Cache-Control", value: "no-store" }] },
      // SECURITY: the setup and reset pages are opened from a link carrying a one-time token (in
      // the fragment, or the query for older links).
      // `no-referrer` means no other site (and no request of ours) ever sees that address in a
      // Referer header. WHY listed last: when two rules set the same header, the last one wins.
      ...["/admin/setup", "/admin/reset"].map((source) => ({
        source,
        headers: [{ key: "Referrer-Policy", value: "no-referrer" }],
      })),
    ];
  },
};

export default nextConfig;
