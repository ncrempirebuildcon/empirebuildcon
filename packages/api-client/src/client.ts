/**
 * Typed API client (openapi-fetch) used by the web app in the browser and on the server.
 *
 * How it works:
 *   1. `createApiClient()` builds a client typed by the generated `paths` (src/schema.d.ts).
 *   2. In the browser the base URL is "" — calls go to `/api/*` on the site and Next.js rewrites
 *      them to the API (handbook/ARCHITECTURE.md §3), so the session cookie stays first-party.
 *   3. A middleware adds `X-CSRF-Token` to every write once `setCsrfToken()` has been called with
 *      the token from `GET /api/v1/auth/me` (handbook/SECURITY.md §3).
 *
 * SECURITY: never store the CSRF token or any session data in localStorage/sessionStorage;
 * it lives only in memory for the lifetime of the page (SECURITY.md §1 "Cookie").
 */
import createClient, { type Client, type Middleware } from "openapi-fetch";
import { ProblemError, isProblem, type Problem } from "./problem";
import type { paths } from "./schema";

const WRITE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export type ApiClient = Client<paths> & {
  /** Remember the CSRF token returned by /auth/me; it is sent on every write. */
  setCsrfToken: (token: string | null) => void;
};

export interface ApiClientOptions {
  /** "" in the browser (same origin). On the server: the API origin, e.g. http://localhost:8000. */
  baseUrl?: string;
  /** Extra headers on every request, e.g. a forwarded session cookie on the server. */
  headers?: Record<string, string>;
  /** Abort requests after this many milliseconds (server fetches use 3000, ARCHITECTURE §3). */
  timeoutMs?: number;
}

export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const { baseUrl = "", headers, timeoutMs } = options;
  let csrfToken: string | null = null;

  const client = createClient<paths>({
    baseUrl,
    headers,
    credentials: "include",
    ...(timeoutMs ? { fetch: withTimeout(timeoutMs) } : {}),
  });

  const csrf: Middleware = {
    onRequest({ request }) {
      if (csrfToken && WRITE_METHODS.has(request.method.toUpperCase())) {
        request.headers.set("X-CSRF-Token", csrfToken);
      }
      return request;
    },
  };
  client.use(csrf);

  return Object.assign(client, {
    setCsrfToken(token: string | null) {
      csrfToken = token;
    },
  });
}

function withTimeout(ms: number): typeof fetch {
  return (input, init) => fetch(input, { ...init, signal: AbortSignal.timeout(ms) });
}

/**
 * Returns `data` from an openapi-fetch result or throws `ProblemError` for an error response.
 * Non-problem error bodies (e.g. a proxy's HTML 502) become a generic problem with the status.
 */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.response.ok) return result.data as T;
  const problem: Problem = isProblem(result.error)
    ? result.error
    : { title: result.response.statusText || "Request failed", status: result.response.status };
  throw new ProblemError(problem);
}
