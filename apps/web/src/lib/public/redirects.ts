/**
 * The CMS's redirects on the website (task 5.6, D-047): proxy.ts asks `findRedirect` for every
 * page request and answers a match with a 301/308, then reports the hit to the API.
 *
 * How it works:
 *   - The active redirects come from GET /api/v1/public/redirects and are kept in this server
 *     process for 60 seconds (PERF: one API call a minute, not one per page; env
 *     REDIRECT_CACHE_SECONDS changes it, the browser tests use 1). A change in the CMS reaches the
 *     website within that minute. WHY not the revalidation tags: the proxy runs in its own bundle,
 *     so the revalidation endpoint can't clear this process's copy.
 *   - PERF: once a list is in hand, no page waits for the API again. An old list is used at once
 *     while a new one loads in the background. Only a process's very first list is waited for,
 *     and then for at most 800 ms. If the API can't be reached, the last list (or none) is kept,
 *     the next try is 10 seconds later, and pages are served as usual (a redirect is never worth
 *     an error page).
 *   - Matching is exact and case-sensitive on the path, after trimming a trailing "/" (the API
 *     stores paths the same way, seo/paths.py) and decoding the visitor's %-escapes (except %2F,
 *     so "/a%2Fb" never matches "/a/b"). The visitor's query string is kept unless the target has
 *     its own, and goes before the target's "#fragment". Next.js's own `_rsc` parameter is dropped.
 *   - The answer may be kept by browsers for an hour (Cache-Control), so a redirect switched off
 *     in the CMS can still apply for a returning visitor for up to that long.
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
const FIRST_LOAD_WAIT_MS = 800;
export const HIT_SIGNATURE_HEADER = "x-redirect-hit-signature";
export const HIT_TIMESTAMP_HEADER = "x-redirect-hit-timestamp";

const NEVER_REDIRECTED = ["/admin", "/api", "/_next", "/_internal", "/brand"];

let cache: { at: number; ttl: number; map: Map<string, ActiveRedirect> } | null = null;
let inFlight: Promise<Map<string, ActiveRedirect>> | null = null;
let generation = 0;

function apiOrigin(): string {
  return process.env.API_ORIGIN ?? "http://localhost:8000";
}

function edgeKeyHeaders(): Record<string, string> {
  const key = process.env.EDGE_PROXY_KEY;
  return key ? { "X-Empire-Edge-Key": key } : {};
}

/** `/a/` → `/a`; `/` stays (seo/paths.py `_trim`). */
export function trimPath(path: string): string {
  return path.replace(/\/+$/, "") || "/";
}

/** The visitor's path as the API stores it: `%C3%A9` → `é`, but `%2F` stays `%2F`. */
export function normalisePath(pathname: string): string {
  let path = pathname;
  try {
    path = decodeURIComponent(pathname.replace(/%2F/gi, "%252F"));
  } catch {
    // A malformed escape is matched as sent.
  }
  return trimPath(path);
}

/** `target` with the visitor's query (no `_rsc`) before its `#fragment`, unless it has one. */
export function locationFor(target: string, search: string): string {
  const params = new URLSearchParams(search);
  params.delete("_rsc");
  const query = params.toString();
  const hashAt = target.indexOf("#");
  const base = hashAt === -1 ? target : target.slice(0, hashAt);
  const hash = hashAt === -1 ? "" : target.slice(hashAt);
  if (!query || base.includes("?")) return target;
  return `${base}?${query}${hash}`;
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
  return new Map(rows.map((r) => [trimPath(r.from_path), r]));
}

function refresh(): Promise<Map<string, ActiveRedirect>> {
  // One load at a time: requests arriving together share it.
  const gen = generation;
  inFlight ??= loadRedirects()
    .then((map) => {
      if (gen === generation) cache = { at: Date.now(), ttl: ttlMs(), map };
      return map;
    })
    .catch(() => {
      const map = cache?.map ?? new Map<string, ActiveRedirect>();
      if (gen === generation) cache = { at: Date.now(), ttl: FAILURE_TTL_MS, map };
      return map;
    })
    .finally(() => {
      if (gen === generation) inFlight = null;
    });
  return inFlight;
}

async function activeRedirects(now = Date.now()): Promise<Map<string, ActiveRedirect>> {
  if (cache) {
    // Stale or not, answer now; an old list starts a refresh in the background.
    if (now - cache.at >= cache.ttl) void refresh();
    return cache.map;
  }
  const empty = new Map<string, ActiveRedirect>();
  const wait = new Promise<Map<string, ActiveRedirect>>((resolve) => {
    setTimeout(() => resolve(empty), FIRST_LOAD_WAIT_MS).unref?.();
  });
  return Promise.race([refresh(), wait]);
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
  return { redirect, location: locationFor(target, search) };
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

/** Tests only: forget the cached redirects; a load still running is ignored. */
export function resetRedirectCache(): void {
  generation += 1;
  cache = null;
  inFlight = null;
}
