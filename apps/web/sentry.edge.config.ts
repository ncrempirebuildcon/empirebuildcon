/**
 * Edge runtime Sentry configuration (Phase 5 Task 5.2).
 *
 * Enabled only when SENTRY_DSN or NEXT_PUBLIC_SENTRY_DSN is set.
 * Scrubs URL queries, fragments, request bodies, cookies and IP addresses before sending.
 */
import * as Sentry from "@sentry/nextjs";
import { beforeSendScrubber } from "@/lib/sentry-scrubber";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN || process.env.SENTRY_DSN || "";

Sentry.init({
  dsn,
  enabled: Boolean(dsn),
  tracesSampleRate: 0.05,
  beforeSend: (event) => beforeSendScrubber(event),
});
