/**
 * Outbox revalidation route verification and execution (Phase 5 Task 5.2).
 *
 * Implements ARCHITECTURE §5:
 *   - Verifies HMAC-SHA256 signature over timestamp + JSON body with REVALIDATE_SECRET.
 *   - Constant-time comparison.
 *   - 5-minute replay window, rejects replayed signatures.
 *   - Calls Next.js revalidateTag for each tag.
 *   - Returns 401 with no detail on missing/invalid signature, stale timestamp, or replay.
 */
import { timingSafeEqual, createHmac } from "node:crypto";
import { revalidateTag } from "next/cache";

export const REVALIDATE_WINDOW_MS = 5 * 60 * 1000;
export const SIGNATURE_HEADER = "x-empire-signature";
export const TIMESTAMP_HEADER = "x-empire-timestamp";

const seenSignatures = new Map<string, number>();

export function _clearReplayCache(): void {
  seenSignatures.clear();
}

function purgeExpired(now: number): void {
  for (const [sig, ts] of seenSignatures.entries()) {
    if (Math.abs(now - ts) > REVALIDATE_WINDOW_MS) {
      seenSignatures.delete(sig);
    }
  }
}

export function computeSignature(secret: string, timestampMs: number, bodyText: string): string {
  const message = `${timestampMs}.${bodyText}`;
  return createHmac("sha256", secret).update(message).digest("hex");
}

export interface RevalidateResult {
  ok: boolean;
  status: number;
  tags?: string[];
}

export async function processRevalidate(
  request: Request,
  options: { secret?: string; now?: number } = {},
): Promise<RevalidateResult> {
  if (request.method !== "POST") {
    return { ok: false, status: 405 };
  }

  const secret = options.secret ?? process.env.REVALIDATE_SECRET;
  if (!secret) {
    return { ok: false, status: 401 };
  }

  const signature = request.headers.get(SIGNATURE_HEADER)?.trim().toLowerCase();
  const timestampHeader = request.headers.get(TIMESTAMP_HEADER)?.trim();

  if (!signature || !timestampHeader) {
    return { ok: false, status: 401 };
  }

  const timestamp = parseInt(timestampHeader, 10);
  if (Number.isNaN(timestamp)) {
    return { ok: false, status: 401 };
  }

  const now = options.now ?? Date.now();
  if (Math.abs(now - timestamp) > REVALIDATE_WINDOW_MS) {
    return { ok: false, status: 401 };
  }

  purgeExpired(now);
  if (seenSignatures.has(signature)) {
    return { ok: false, status: 401 };
  }

  const bodyText = await request.text();
  const expectedHex = computeSignature(secret, timestamp, bodyText).toLowerCase();

  try {
    const sigBuf = Buffer.from(signature, "hex");
    const expBuf = Buffer.from(expectedHex, "hex");
    if (sigBuf.length !== expBuf.length || !timingSafeEqual(sigBuf, expBuf)) {
      return { ok: false, status: 401 };
    }
  } catch {
    return { ok: false, status: 401 };
  }

  let tags: string[] = [];
  try {
    const json = JSON.parse(bodyText);
    if (Array.isArray(json?.tags)) {
      tags = json.tags.filter((t: unknown): t is string => typeof t === "string" && t.length > 0);
    }
  } catch {
    return { ok: false, status: 401 };
  }

  if (tags.length === 0) {
    return { ok: false, status: 401 };
  }

  seenSignatures.set(signature, timestamp);

  for (const tag of tags) {
    try {
      revalidateTag(tag, "default");
    } catch {
      // Ignore in environments where cache is inactive
    }
  }

  return { ok: true, status: 200, tags };
}

export async function revalidateHandler(request: Request): Promise<Response> {
  const result = await processRevalidate(request);
  if (!result.ok) {
    return new Response(null, { status: result.status });
  }
  return new Response(JSON.stringify({ revalidated: true, tags: result.tags }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
