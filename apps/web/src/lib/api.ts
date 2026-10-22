/**
 * Browser API client: same-origin calls to /api/*, rewritten by Next.js to the API
 * (handbook/ARCHITECTURE.md §3). One instance per page load; the CSRF token lives in memory.
 *
 * Every CMS screen calls the API through `call()`, so a session that ended while the page was
 * open sends the user back to sign in instead of showing a confusing error.
 */
import { createApiClient, unwrap, type components, type paths } from "@empire/api-client";
import { SIGN_IN_PATH } from "./routes";

export const api = createApiClient();

// SECURITY: memory only, never localStorage (SECURITY.md §1). The XHR uploads (lib/media/upload.ts)
// need the token too, because they send multipart bodies with progress, which fetch can't report.
let csrfToken: string | null = null;

/** Remember the session's CSRF token for every write (the shell sets it from /auth/me). */
export function setCsrfToken(token: string | null): void {
  csrfToken = token;
  api.setCsrfToken(token);
}

/** The CSRF token for a write made outside the generated client (XHR uploads). */
export function currentCsrfToken(): string | null {
  return csrfToken;
}

/** The signed-in staff member, as returned by GET /api/v1/auth/me. */
export type SessionUser =
  paths["/api/v1/auth/me"]["get"]["responses"][200]["content"]["application/json"];

/** A schema from the generated client, e.g. `Schema<"ProjectAdmin">` (never hand-written). */
export type Schema<Name extends keyof components["schemas"]> = components["schemas"][Name];

/**
 * Awaits an openapi-fetch call and returns its data, or throws `ProblemError`.
 * A 401 (session expired or revoked) also starts a full navigation to the sign-in page.
 */
export async function call<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const result = await request;
  if (result.response.status === 401 && typeof window !== "undefined") {
    window.location.assign(SIGN_IN_PATH);
  }
  return unwrap(result);
}
