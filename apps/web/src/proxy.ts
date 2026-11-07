/**
 * Next.js proxy (Next 16's name for middleware) for /api/* and page requests.
 *
 * How it works:
 *   1. /api/v1/internal/* is never reachable through the website (the scheduler calls the API
 *      host directly with its own key) → 404 here.
 *   2. Any X-Empire-* header the visitor sent is removed, so nobody can pretend to be us.
 *   3. With EDGE_PROXY_KEY set (staging, production) we add (ONLY for /api/* requests):
 *        X-Empire-Edge-Key  — the shared secret the API checks (apps/api middleware/edge_guard.py)
 *        X-Empire-Client-IP — the visitor's address as seen by the hosting platform, read from
 *                             the header named in CLIENT_IP_SOURCE_HEADER.
 *      Locally (no key) nothing is added and the API uses the socket address.
 *   4. For page requests: a redirect made in the CMS answers first (301/308, counted; task 5.6,
 *      lib/public/redirects.ts). Otherwise a per-request cryptographically random nonce is made
 *      and Content-Security-Policy is set (enforced in production and when CSP_ENFORCE=true;
 *      report-only otherwise, so staging can collect reports first). Ad and analytics hosts are
 *      added only for the platforms in TRACKING_CSP (task 6.3, D-058, lib/tracking/platforms.ts).
 *   5. On staging and production, an /api/* call whose host gave no client IP is refused (503).
 *
 * SECURITY / DO NOT CHANGE without owner approval:
 *   - The API trusts X-Empire-Client-IP only because this file is the only thing that can set it.
 *     Never read the IP from the visitor's X-Forwarded-For here, and never expose EDGE_PROXY_KEY.
 *   - CSP protects against XSS and data exfiltration (SECURITY.md §4).
 *   TODO(phase-9): confirm on Netlify staging which header carries the client IP for the proxy
 *   (x-nf-client-connection-ip by default) and record it in handbook/RUNBOOK.md.
 */
import { NextResponse, type NextFetchEvent, type NextRequest } from "next/server";
import { CLIENT_IP_HEADER, EDGE_KEY_HEADER, edgeHeaders } from "./lib/edge";
import { findRedirect, reportHit } from "./lib/public/redirects";
import { allowedPlatforms, cspSources } from "./lib/tracking/platforms";

function buildCsp(options: { nonce?: string; tracking?: boolean }): string {
  const isDev = process.env.NODE_ENV !== "production";
  const sentryDsn = process.env.NEXT_PUBLIC_SENTRY_DSN || process.env.SENTRY_DSN || "";
  let sentryHost = "";
  if (sentryDsn) {
    try {
      sentryHost = `https://${new URL(sentryDsn).host}`;
    } catch {
      sentryHost = "https://*.ingest.sentry.io";
    }
  }

  // Ad and analytics hosts, only for the platforms TRACKING_CSP lists (task 6.3, D-058;
  // lib/tracking/platforms.ts). Empty by default, so the launch CSP is unchanged.
  // SECURITY: never on /admin, where no tag runs: an allowed script host is also one an injected
  // tag could load from, and the CMS holds lead data (6.3 review).
  const tracking = cspSources(
    options.tracking ? allowedPlatforms(process.env.TRACKING_CSP) : new Set(),
  );
  const extra = (hosts: string[]) => (hosts.length ? ` ${hosts.join(" ")}` : "");

  const scriptSrc = options.nonce
    ? `script-src 'self' 'nonce-${options.nonce}'${extra(tracking.script)} ${isDev ? "'unsafe-eval'" : ""}`.trim()
    : `script-src 'self' 'unsafe-inline'${extra(tracking.script)} ${isDev ? "'unsafe-eval'" : ""}`.trim();

  const directives = [
    "default-src 'self'",
    scriptSrc,
    "style-src 'self' 'unsafe-inline'",
    // OpenStreetMap tiles for the project map (task 5.3, D-041; the map loads only on tap).
    `img-src 'self' https://res.cloudinary.com data: blob: https://tile.openstreetmap.org${extra(tracking.img)}`,
    "font-src 'self'",
    `connect-src 'self' https://api.cloudinary.com ${sentryHost}${extra(tracking.connect)}`
      .replace(/\s+/g, " ")
      .trim(),
    ...(tracking.frame.length ? [`frame-src 'self'${extra(tracking.frame)}`] : []),
    "media-src 'self' https://res.cloudinary.com blob:",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "report-uri /_internal/csp-report",
  ];

  return directives.join("; ");
}

export async function proxy(request: NextRequest, event: NextFetchEvent) {
  // Bypass proxy for internal routes (M1)
  const pathname = request.nextUrl.pathname;
  if (pathname.startsWith("/_internal/")) {
    return NextResponse.next();
  }

  // 1. Block internal API calls. SECURITY (L2 security review): matched on the decoded path,
  // because the API decodes "%2F" and "%69": "/api/v1/internal%2Foutbox" is the same route.
  // Decoded until it stops changing, so "%252F" can't hide a slash either; page paths aren't
  // decoded here (a page URL with a stray "%" still reaches its 404).
  let decoded = pathname;
  if (pathname.toLowerCase().startsWith("/api")) {
    try {
      for (let i = 0; i < 3 && decoded.includes("%"); i += 1) decoded = decodeURIComponent(decoded);
    } catch {
      return new NextResponse(null, { status: 400 });
    }
  }
  if (decoded.startsWith("/api/v1/internal/") || decoded === "/api/v1/internal") {
    return NextResponse.json(
      { type: "about:blank", title: "Not Found", status: 404, detail: "Not found." },
      { status: 404, headers: { "content-type": "application/problem+json" } },
    );
  }

  // 2. Strip visitor x-empire-* headers
  const headers = new Headers(request.headers);
  for (const name of [...headers.keys()]) {
    if (name.startsWith("x-empire-")) headers.delete(name);
  }

  // 3. For /api/* calls: attach edge headers and forward (MM2, S3, Note 7)
  if (pathname === "/api" || pathname.startsWith("/api/")) {
    const edge = edgeHeaders((n) => request.headers.get(n));
    // SECURITY (L2 security review): on staging and production, a browser call must carry the
    // visitor's IP (tests and local runs have no hosting platform to add it). Without it the API would count every visitor under the web host's own
    // address: one stranger could then use up the shared sign-in, reset and enquiry limits for
    // everybody. A missing header is a hosting misconfiguration, so fail closed and say so.
    const hosted = process.env.APP_ENV === "staging" || process.env.APP_ENV === "production";
    if (hosted && edge[EDGE_KEY_HEADER] && !edge[CLIENT_IP_HEADER]) {
      console.error(
        `[edge] no client IP in ${process.env.CLIENT_IP_SOURCE_HEADER ?? "x-nf-client-connection-ip"}; refusing /api call`,
      );
      return NextResponse.json(
        {
          type: "about:blank",
          title: "Service Unavailable",
          status: 503,
          detail: "Please try again in a minute.",
        },
        { status: 503, headers: { "content-type": "application/problem+json" } },
      );
    }
    for (const [name, value] of Object.entries(edge)) {
      headers.set(name, value);
    }
    return NextResponse.next({ request: { headers } });
  }

  // 4a. A redirect from the CMS (task 5.6, D-047). Only GET and HEAD: a form post is never
  // sent elsewhere. SECURITY: the target is a path on this site (lib/public/redirects.ts), made
  // absolute on SITE_URL, so `Location` never depends on the Host header the visitor sent.
  // (Next.js refuses a relative Location here.)
  if (request.method === "GET" || request.method === "HEAD") {
    const found = await findRedirect(pathname, request.nextUrl.search);
    if (found) {
      // A browser prefetch is not a visit, so it is not counted. WHY only the browser's own
      // headers: Next.js removes its router headers (next-router-prefetch, rsc) before the proxy
      // runs, so a <Link> prefetch of an old address can't be told apart and may be counted.
      const prefetch =
        request.headers.get("purpose") === "prefetch" ||
        request.headers.get("sec-purpose")?.includes("prefetch");
      if (!prefetch && request.method === "GET") {
        event.waitUntil(reportHit(found.redirect.from_path));
      }
      return new NextResponse(null, {
        status: found.redirect.status_code === 301 ? 301 : 308,
        headers: {
          Location: new URL(found.location, process.env.SITE_URL || request.nextUrl.origin).href,
          "Cache-Control": "private, max-age=3600",
        },
      });
    }
  }

  // 4b. For page requests: attach CSP (MM2, S3, S4, R2-M3)
  const isStaticAuth =
    pathname === "/admin/setup" || pathname === "/admin/reset" || pathname === "/admin/forgot";

  // Static auth pages are pre-rendered at build time so tokens never appear in server HTML (SECURITY §1);
  // they carry a strict policy with 'self' 'unsafe-inline' so frame-ancestors, object-src,
  // base-uri and connect-src are strictly enforced by CSP (R2-M3).
  // Dynamic pages (CMS, public shell, 404) use a cryptographically random per-request nonce.
  const nonce = isStaticAuth ? undefined : Buffer.from(crypto.randomUUID()).toString("base64");
  const isAdmin = pathname === "/admin" || pathname.startsWith("/admin/");
  const csp = buildCsp({ nonce, tracking: !isAdmin });
  // SECURITY (L2 security review): production enforces the policy unless CSP_ENFORCE=false is
  // set on purpose; staging stays report-only until CSP_ENFORCE=true (D-039's week of reports).
  const enforce =
    process.env.CSP_ENFORCE === "true" ||
    (process.env.APP_ENV === "production" && process.env.CSP_ENFORCE !== "false");
  const cspHeaderName = enforce ? "Content-Security-Policy" : "Content-Security-Policy-Report-Only";

  if (nonce) {
    headers.set("x-nonce", nonce);
  }
  headers.set(cspHeaderName, csp);

  const response = NextResponse.next({ request: { headers } });
  response.headers.set(cspHeaderName, csp);
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|_internal/).*)"],
};
