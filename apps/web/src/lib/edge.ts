/**
 * Headers that prove a request to the API comes from this web app (see src/proxy.ts and
 * apps/api/src/empire_api/middleware/edge_guard.py). Used by the /api/* proxy for browser calls
 * and by Server Components that call the API directly (e.g. the CMS session check).
 *
 * SECURITY: server-only. EDGE_PROXY_KEY must never be exposed as NEXT_PUBLIC_* or sent to the
 * browser. Without it (local development) no headers are added and the API uses the socket address.
 */
export const EDGE_KEY_HEADER = "x-empire-edge-key";
export const CLIENT_IP_HEADER = "x-empire-client-ip";

/** Edge headers for one request; `incoming` reads a header of the visitor's request. */
export function edgeHeaders(incoming: (name: string) => string | null): Record<string, string> {
  const key = process.env.EDGE_PROXY_KEY;
  if (!key) return {};
  const out: Record<string, string> = { [EDGE_KEY_HEADER]: key };
  const source = (process.env.CLIENT_IP_SOURCE_HEADER ?? "x-nf-client-connection-ip").toLowerCase();
  const ip = incoming(source)?.trim();
  if (ip) out[CLIENT_IP_HEADER] = ip;
  return out;
}
