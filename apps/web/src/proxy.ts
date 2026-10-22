/**
 * Next.js proxy (Next 16's name for middleware) for /api/* — runs before the rewrite in
 * next.config.ts forwards the request to the API.
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
 *
 * SECURITY / DO NOT CHANGE without owner approval: the API trusts X-Empire-Client-IP only
 * because this file is the only thing that can set it. Never read the IP from the visitor's
 * X-Forwarded-For here (they can forge it), and never expose EDGE_PROXY_KEY as NEXT_PUBLIC_*.
 * TODO(phase-9): confirm on Netlify staging which header carries the client IP for the proxy
 * (x-nf-client-connection-ip by default) and record it in handbook/RUNBOOK.md.
 */
import { NextResponse, type NextRequest } from "next/server";
import { edgeHeaders } from "./lib/edge";

export function proxy(request: NextRequest) {
  if (request.nextUrl.pathname.startsWith("/api/v1/internal/")) {
    return NextResponse.json(
      { type: "about:blank", title: "Not Found", status: 404, detail: "Not found." },
      { status: 404, headers: { "content-type": "application/problem+json" } },
    );
  }

  const headers = new Headers(request.headers);
  for (const name of [...headers.keys()]) {
    if (name.startsWith("x-empire-")) headers.delete(name);
  }

  for (const [name, value] of Object.entries(edgeHeaders((n) => request.headers.get(n)))) {
    headers.set(name, value);
  }

  return NextResponse.next({ request: { headers } });
}

export const config = {
  matcher: ["/api/:path*"],
};
