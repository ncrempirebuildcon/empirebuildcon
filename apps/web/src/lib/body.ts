/**
 * Reads a request body as text, stopping as soon as it passes a byte limit.
 *
 * SECURITY (L2 security review): `request.text()` reads the whole body before anyone can check
 * its size, and a chunked request has no Content-Length to check first. The unsigned
 * `/_internal/*` routes use this instead, so a large anonymous POST costs at most `maxBytes`.
 * Used by lib/public/revalidate.ts and app/_internal/csp-report/route.ts.
 */
export async function readCapped(request: Request, maxBytes: number): Promise<string | null> {
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maxBytes) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  return new TextDecoder().decode(Buffer.concat(chunks));
}
