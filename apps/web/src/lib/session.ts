/**
 * Server-side session check for CMS pages. Import only from Server Components.
 *
 * How it works:
 *   1. Read the session cookie from the incoming request (it is HttpOnly, so only the server sees it).
 *   2. Call the API's /api/v1/auth/me directly at API_ORIGIN with that cookie and a 3-second timeout
 *      (ARCHITECTURE.md §3: the API may be slow to wake on free hosting).
 *   3. 401 means signed out (return null); any other failure is thrown so error.tsx shows "Try again".
 *
 * SECURITY: only the session cookie is forwarded, never the visitor's other cookies; the edge
 * headers (lib/edge.ts) are added so the API accepts the call.
 */
import { cookies, headers as requestHeaders } from "next/headers";
import { createApiClient, unwrap } from "@empire/api-client";
import type { SessionUser } from "./api";
import { edgeHeaders } from "./edge";

// DO NOT CHANGE: the cookie name is fixed by the API (SECURITY.md §1); the __Host- prefix makes
// browsers refuse it unless it is Secure, host-only and Path=/.
export const SESSION_COOKIE = "__Host-empire_session";

export async function getSessionUser(): Promise<SessionUser | null> {
  const session = (await cookies()).get(SESSION_COOKIE);
  if (!session) return null;

  const incoming = await requestHeaders();
  const api = createApiClient({
    baseUrl: process.env.API_ORIGIN ?? "http://localhost:8000",
    // SECURITY: the edge headers prove this call comes from our server (proxy.ts explains why).
    headers: {
      cookie: `${SESSION_COOKIE}=${session.value}`,
      ...edgeHeaders((n) => incoming.get(n)),
    },
    timeoutMs: 3000,
  });
  const result = await api.GET("/api/v1/auth/me");
  if (result.response.status === 401) return null;
  return unwrap(result);
}
