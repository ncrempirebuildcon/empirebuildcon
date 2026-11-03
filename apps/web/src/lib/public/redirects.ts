/**
 * The CMS's redirects on the website (task 5.6, D-047): proxy.ts asks `findRedirect` for every
 * page request and answers a match with a 301/308, then reports the hit to the API.
 *
 * How it works:
 *   - The active redirects come from GET /api/v1/public/redirects and are kept in this server
 *     process for 60 seconds (PERF: one API call a minute, not one per page; env
 *     REDIRECT_CACHE_SECONDS changes it, the browser tests use 1). A change in the CMS reaches the
 *     website within that minute. WHY not the revalidation tags: the proxy runs in its own bundle,
 *     so the revalidation endpoint can't clear this process's copy. If the API can't be reached, no redirect is applied
 *     for 10 seconds and pages are served as usual (a redirect is never worth an error page).
 *   - Matching is exact on the path, after trimming a trailing "/" (the API stores paths the same
 *     way, seo/paths.py) and decoding %-escapes. The visitor's query string is kept unless the
 *     target has its own.
 *   - Each redirect served is counted by a signed POST to /api/v1/internal/redirects/hit
 *     (apps/api seo/hits.py), sent after the answer (`waitUntil`), so a slow API never slows a
 *     redirect. A failed report is dropped: counts are for staff insight only.
 *
 * SECURITY (SECURITY.md §5): the API only stores targets that are paths on this site (one "/",
 * no backslash), and `safeTarget` checks again here, so a redirect can never send a visitor to
 * another host. /admin, /api and the site's own files are never redirected.
 */
import { createHmac } from "node:crypto";

export interface ActiveRedirect {
  from_path: string;
  to_path: string;
  status_code: number;
}

function ttlMs(): number {
  const raw = process.env.REDIRECT_CACHE_SECONDS?.trim();
  const seconds = raw ? Number(raw) : 60;
  return Number.isFinite(seconds) && seconds >= 0 ? seconds * 1000 : 60_000;
}
const FAILURE_TTL_MS = 10_000;
const FETCH_TIMEOUT_MS = 1_500;
export const HIT_SIGNATURE_HEADER = "x-redirect-hit-signature";
export const HIT_TIMESTAMP_HEADER = "x-redirect-hit-timestamp";

const NEVER_REDIRECTED = ["/admin", "/api", "/_next", "/_internal", "/brand"];

let cache: { at: number; ttl: number; map: Map<string, ActiveRedirect> } | null = null;
let inFlight: Promise<Map<string, ActiveRedirect>> | null = null;

function apiOrigin(): string {
  return process.env.API_ORIGIN ?? "http://localhost:8000";
}

function edgeKeyHeaders(): Record<string, string> {
  const key = process.env.EDGE_PROXY_KEY;
  return key ? { "X-Empire-Edge-Key": key } : {};
}

/** `/a/` → `/a`, `%C3%A9` → `é`; `/` stays. */
export function normalisePath(pathname: string): string {
  let path = pathname;
  try {
    path = decodeURIComponent(pathname);
  } catch {
    // A malformed escape is matched as sent.
  }
  const trimmed = path.replace(/\/+$/, "");
  return trimmed || "/";
}

/** A target that is a path on this site, or null (SECURITY.md §5). */
export function safeTarget(to: string): string | null {
  if (!to.startsWith("/") || to.startsWith("//") || /[\\\u0000- ]/.test(to)) return null;
  return to;
}

export function isRedirectable(pathname: string): boolean {
  if (pathname === "/") return false;
  const lower = pathname.toLowerCase();
  return !NEVER_REDIRECTED.some((p) => lower === p || lower.startsWith(`${p}/`));
}

async function loadRedirects(): Promise<Map<string, ActiveRedirect>> {
  const response = await fetch(`${apiOrigin()}/api/v1/public/redirects`, {
    headers: { Accept: "application/json", ...edgeKeyHeaders() },
    cache: "no-store",
    signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
  });
  if (!response.ok) throw new Error(`redirects: HTTP ${response.status}`);
  const rows = (await response.json()) as ActiveRedirect[];
  return new Map(rows.map((r) => [normalisePath(r.from_path), r]));
}

async function activeRedirects(now = Date.now()): Promise<Map<string, ActiveRedirect>> {
  if (cache && now - cache.at < cache.ttl) return cache.map;
  // One load at a time: requests arriving together wait for the same answer.
  inFlight ??= loadRedirects()
    .then((map) => {
      cache = { at: Date.now(), ttl: ttlMs(), map };
      return map;
    })
    .catch(() => {
      const map = cache?.map ?? new Map<string, ActiveRedirect>();
      cache = { at: Date.now(), ttl: FAILURE_TTL_MS, map };
      return map;
    })
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}

/** The redirect for this request, with the final `Location` path, or null. */
export async function findRedirect(
  pathname: string,
  search: string,
): Promise<{ redirect: ActiveRedirect; location: string } | null> {
  if (!isRedirectable(pathname)) return null;
  const redirect = (await activeRedirects()).get(normalisePath(pathname));
  if (!redirect) return null;
  const target = safeTarget(redirect.to_path);
  if (!target) return null;
  const location = target.includes("?") || !search ? target : `${target}${search}`;
  return { redirect, location };
}

/** HMAC-SHA256 over `redirect-hit.{timestamp}.{body}` with REVALIDATE_SECRET (seo/hits.py). */
export function hitSignature(secret: string, timestampMs: number, body: string): string {
  return createHmac("sha256", secret).update(`redirect-hit.${timestampMs}.${body}`).digest("hex");
}

/** Reports one served redirect. Never throws. */
export async function reportHit(fromPath: string): Promise<void> {
  const secret = process.env.REVALIDATE_SECRET;
  if (!secret) return;
  const body = JSON.stringify({ from_path: fromPath });
  const ts = Date.now();
  try {
    await fetch(`${apiOrigin()}/api/v1/internal/redirects/hit`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        [HIT_SIGNATURE_HEADER]: hitSignature(secret, ts, body),
        [HIT_TIMESTAMP_HEADER]: String(ts),
      },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
  } catch {
    // Dropped: see the module header.
  }
}

/** Tests only: forget the cached redirects. */
export function resetRedirectCache(): void {
  cache = null;
  inFlight = null;
}
