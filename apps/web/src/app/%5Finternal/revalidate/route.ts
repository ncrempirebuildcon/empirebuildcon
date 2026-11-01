/**
 * Signed cache revalidation endpoint: POST /_internal/revalidate (outside /api/*).
 *
 * Implements ARCHITECTURE §5:
 *   - Verifies HMAC-SHA256 signature with REVALIDATE_SECRET.
 *   - Constant-time compare, 5-minute replay window.
 *   - Anything unsigned or stale gets 401 with no detail.
 */
import { revalidateHandler } from "@/lib/public/revalidate";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  return revalidateHandler(request);
}
