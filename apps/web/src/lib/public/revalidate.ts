/**
 * Outbox revalidation route verification and execution (Phase 5 Task 5.2).
 *
 * Implements ARCHITECTURE §5 & D-039:
 *   - Verifies HMAC-SHA256 signature over timestamp + JSON body with REVALIDATE_SECRET.
 *   - Constant-time comparison using Buffer.timingSafeEqual.
 *   - Header names: `x-revalidate-signature` and `x-revalidate-timestamp` (M1).
 *   - Strict hex signature validation (/^[0-9a-f]{64}$/) to prevent non-hex replay bypasses (M3).
 *   - Replay cache keyed on the verified HMAC signature (M3).
 *   - In-memory replay cache is best-effort per instance; the 5-minute window is the primary
 *     replay boundary (N1).
 *   - Request body capped at 16 KB (N2).
 *   - Calls Next.js revalidateTag for each tag.
 *   - Returns 401 with no detail on missing/invalid signature, stale timestamp, or replay.
 */
import { timingSafeEqual, createHmac } from "node:crypto";
import { revalidateTag, revalidatePath } from "next/cache";

export const REVALIDATE_WINDOW_MS = 5 * 60 * 1000;
export const MAX_REVALIDATE_BODY_BYTES = 16 * 1024;

export const SIGNATURE_HEADER = "x-revalidate-signature";
export const TIMESTAMP_HEADER = "x-revalidate-timestamp";

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

  // 1. Read headers (x-revalidate-*)
  const signatureRaw = (request.headers.get(SIGNATURE_HEADER) ?? "").trim();
  const timestampRaw = (request.headers.get(TIMESTAMP_HEADER) ?? "").trim();

  if (!signatureRaw || !timestampRaw) {
    return { ok: false, status: 401 };
  }

  // 2. Strict format check: exactly 64 hex characters (M3)
  if (!/^[0-9a-f]{64}$/i.test(signatureRaw)) {
    return { ok: false, status: 401 };
  }
  const signature = signatureRaw.toLowerCase();

  // 3. Timestamp parsing & freshness window check
  const timestamp = parseInt(timestampRaw, 10);
  if (Number.isNaN(timestamp)) {
    return { ok: false, status: 401 };
  }

  const now = options.now ?? Date.now();
  if (Math.abs(now - timestamp) > REVALIDATE_WINDOW_MS) {
    return { ok: false, status: 401 };
  }

  // 4. Check Content-Length cap if provided (N2)
  const contentLength = parseInt(request.headers.get("content-length") || "0", 10);
  if (contentLength > MAX_REVALIDATE_BODY_BYTES) {
    return { ok: false, status: 401 };
  }

  // 5. Purge expired entries and check replay cache
  purgeExpired(now);
  if (seenSignatures.has(signature)) {
    return { ok: false, status: 401 };
  }

  // 6. Read body and enforce size cap
  const bodyText = await request.text();
  if (bodyText.length > MAX_REVALIDATE_BODY_BYTES) {
    return { ok: false, status: 401 };
  }

  // 7. Verify HMAC signature in constant time
  const expectedHex = computeSignature(secret, timestamp, bodyText).toLowerCase();
  if (seenSignatures.has(expectedHex)) {
    return { ok: false, status: 401 };
  }

  try {
    const sigBuf = Buffer.from(signature, "hex");
    const expBuf = Buffer.from(expectedHex, "hex");
    if (sigBuf.length !== expBuf.length || !timingSafeEqual(sigBuf, expBuf)) {
      return { ok: false, status: 401 };
    }
  } catch {
    return { ok: false, status: 401 };
  }

  // 8. Parse tags
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

  // 9. Record in replay cache keyed on the verified expected signature (M3)
  seenSignatures.set(expectedHex, timestamp);

  // 10. Revalidate tags (Note 1)
  for (const tag of tags) {
    try {
      (revalidateTag as unknown as (t: string, opts?: { expire: number }) => void)(tag, {
        expire: 0,
      });
    } catch {
      // Ignore in test or environments where cache is inactive
    }
  }

  try {
    revalidatePath("/");
  } catch {
    // Ignore in test or environments where cache is inactive
  }

  return { ok: true, status: 200, tags };
}

export async function revalidateHandler(request: Request): Promise<Response> {
  const result = await processRevalidate(request);
  if (!result.ok) {
    return new Response(null, { status: result.status });
  }
  return Response.json({ revalidated: true, tags: result.tags });
}
