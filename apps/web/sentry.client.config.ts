/**
 * Client-side Sentry configuration (Phase 5 Task 5.2, M4, M5).
 *
 * Enabled only when NEXT_PUBLIC_SENTRY_DSN is set.
 * Scrubs URL queries, fragments, request bodies, cookies and IP addresses before sending.
 */
import * as Sentry from "@sentry/nextjs";
import {
  beforeBreadcrumbScrubber,
  beforeSendScrubber,
  beforeSendTransactionScrubber,
} from "@/lib/sentry-scrubber";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN || "";

Sentry.init({
  dsn,
  enabled: Boolean(dsn),
  tracesSampleRate: 0.05,
  dataCollection: {
    userInfo: false,
    cookies: false,
    httpHeaders: false,
    httpBodies: [],
    urlQueryParams: false,
    databaseQueryData: false,
  },
  beforeSend: (event) => beforeSendScrubber(event),
  beforeSendTransaction: (event) => beforeSendTransactionScrubber(event),
  beforeBreadcrumb: (breadcrumb) => beforeBreadcrumbScrubber(breadcrumb),
});
