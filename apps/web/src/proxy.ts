/**
 * Next.js proxy (Next 16's name for middleware) for /api/* and page requests.
 *
 * How it works:
 *   1. /api/v1/internal/* is never reachable through the website (the scheduler calls the API
 *      host directly with its own key) → 404 here.
 *   2. Any X-Empire-* header the visitor sent is removed, so nobody can pretend to be us.
 *   3. With EDGE_PROXY_KEY set (staging, production) we add:
 *        X-Empire-Edge-Key  — the shared secret the API checks (apps/api middleware/edge_guard.py)
 *        X-Empire-Client-IP — the visitor's address as seen by the hosting platform, read from
 *                             the header named in CLIENT_IP_SOURCE_HEADER.
 *      Locally (no key) nothing is added and the API uses the socket address.
 *   4. For page requests: generates a per-request cryptographically random nonce and sets
 *      Content-Security-Policy (report-only by default; enforced when CSP_ENFORCE=true).
 *
 * SECURITY / DO NOT CHANGE without owner approval:
 *   - The API trusts X-Empire-Client-IP only because this file is the only thing that can set it.
 *     Never read the IP from the visitor's X-Forwarded-For here, and never expose EDGE_PROXY_KEY.
 *   - CSP protects against XSS and data exfiltration (SECURITY.md §4).
 */
import { NextResponse, type NextRequest } from "next/server";
import { edgeHeaders } from "./lib/edge";

function buildCsp(nonce?: string): string {
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

  const scriptSrc = nonce
    ? `script-src 'self' 'nonce-${nonce}' ${isDev ? "'unsafe-eval'" : ""}`.trim()
    : `script-src 'self' 'unsafe-inline' ${isDev ? "'unsafe-eval'" : ""}`.trim();

  const directives = [
    "default-src 'self'",
    scriptSrc,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' https://res.cloudinary.com data:",
    "font-src 'self'",
    `connect-src 'self' https://api.cloudinary.com ${sentryHost}`.trim(),
    "frame-ancestors 'none'",
    "form-action 'self'",
    "object-src 'none'",
    "base-uri 'self'",
  ];

  return directives.join("; ");
}

export function proxy(request: NextRequest) {
  // 1. Block internal API calls
  if (request.nextUrl.pathname.startsWith("/api/v1/internal/")) {
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

  // 3. Attach edge authentication headers
  for (const [name, value] of Object.entries(edgeHeaders((n) => request.headers.get(n)))) {
    headers.set(name, value);
  }

  // If this is an API call, forward with edge headers and exit
  if (request.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.next({ request: { headers } });
  }

  // 4. Generate CSP
  // Static auth pages (setup, reset, forgot) are pre-rendered at build time so tokens
  // never appear in server HTML (SECURITY §1); dynamic pages and CMS use per-request nonce.
  const isStaticAuth =
    request.nextUrl.pathname === "/admin/setup" ||
    request.nextUrl.pathname === "/admin/reset" ||
    request.nextUrl.pathname === "/admin/forgot";

  const nonce = isStaticAuth ? undefined : Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = buildCsp(nonce);
  const enforce = process.env.CSP_ENFORCE === "true";
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
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
