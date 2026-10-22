/**
 * Browser API client: same-origin calls to /api/*, rewritten by Next.js to the API
 * (handbook/ARCHITECTURE.md §3). One instance per page load; the CSRF token lives in memory.
 */
import { createApiClient, type paths } from "@empire/api-client";

export const api = createApiClient();

/** The signed-in staff member, as returned by GET /api/v1/auth/me. */
export type SessionUser =
  paths["/api/v1/auth/me"]["get"]["responses"][200]["content"]["application/json"];
