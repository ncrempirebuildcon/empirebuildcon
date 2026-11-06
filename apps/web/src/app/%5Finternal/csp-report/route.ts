/**
 * CSP violation report endpoint (Phase 5 Task 5.2, S4, S-N5).
 *
 * Receives CSP reports sent via `report-uri /_internal/csp-report`.
 * Logs compact, PII-free violation details on development and staging without logging IPs or queries.
 */
import { NextResponse, type NextRequest } from "next/server";
import { readCapped } from "@/lib/body";
import { sanitizeUrl } from "@/lib/sentry-scrubber";

const MAX_BODY_BYTES = 16 * 1024; // 16 KB cap (S-N5)

export async function POST(request: NextRequest) {
  try {
    const contentLength = parseInt(request.headers.get("content-length") ?? "0", 10);
    if (contentLength > MAX_BODY_BYTES) {
      return new NextResponse(null, { status: 413 });
    }

    const text = await readCapped(request, MAX_BODY_BYTES);
    if (text === null) {
      return new NextResponse(null, { status: 413 });
    }

    const json = JSON.parse(text) as Record<string, unknown> | null;
    const report =
      (json?.["csp-report"] as Record<string, unknown> | undefined) ??
      (json?.["report"] as Record<string, unknown> | undefined) ??
      json;

    if (report && process.env.APP_ENV !== "production") {
      const directive = report["effective-directive"] || report["violated-directive"] || "unknown";
      const blockedUri = sanitizeUrl(String(report["blocked-uri"] ?? "")) ?? "unknown";
      const documentUri = sanitizeUrl(String(report["document-uri"] ?? "")) ?? "unknown";

      console.warn("[CSP Violation]", {
        directive,
        blockedUri,
        documentUri,
      });
    }
  } catch {
    // Ignore invalid or malformed report payloads
  }
  return new NextResponse(null, { status: 204 });
}
