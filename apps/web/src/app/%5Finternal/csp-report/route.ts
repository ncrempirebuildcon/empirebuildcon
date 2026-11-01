/**
 * CSP violation report endpoint (Phase 5 Task 5.2, S4).
 *
 * Receives CSP reports sent via `report-uri /_internal/csp-report`
 * or `report-to` directives. Logs violation details without leaking PII.
 */
import { NextResponse, type NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  try {
    const report = await request.json().catch(() => null);
    if (report && process.env.NODE_ENV !== "production") {
      // In dev/staging, log violations to assist debugging
      console.warn("[CSP Violation]", JSON.stringify(report));
    }
  } catch {
    // Ignore invalid report payloads
  }
  return new NextResponse(null, { status: 204 });
}
