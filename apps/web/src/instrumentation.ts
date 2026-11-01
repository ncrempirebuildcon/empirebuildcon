/**
 * Next.js Instrumentation hook (Phase 5 Task 5.2, M4).
 *
 * Initializes Sentry server and edge configurations in the appropriate runtimes
 * and exports onRequestError for server error reporting.
 */
import * as Sentry from "@sentry/nextjs";

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("../sentry.server.config");
  }

  if (process.env.NEXT_RUNTIME === "edge") {
    await import("../sentry.edge.config");
  }
}

export const onRequestError = Sentry.captureRequestError;
