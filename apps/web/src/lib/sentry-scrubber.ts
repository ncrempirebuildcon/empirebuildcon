/**
 * Sentry data scrubber (SECURITY §8, Phase 5 Task 5.2, M5).
 *
 * Implements:
 *   - Drops query strings and fragments from every URL (prevents leaking lead ?q= numbers, tokens).
 *   - Deletes `request.query_string`, `request.env`, and `event.user` entirely.
 *   - Uses a strict allowlist for request headers, sanitizing `referer` and stripping secrets/PII.
 *   - Provides `beforeSend`, `beforeSendTransaction`, and `beforeBreadcrumb` scrubbers.
 */

const ALLOWED_HEADERS = new Set([
  "accept",
  "accept-language",
  "content-type",
  "referer",
  "user-agent",
]);

export function sanitizeUrl(rawUrl?: string | null): string | undefined {
  if (!rawUrl) return undefined;
  try {
    const dummyOrigin = "https://empirebuildcon.com";
    const parsed = new URL(rawUrl, dummyOrigin);
    if (rawUrl.startsWith("/")) {
      return parsed.pathname;
    }
    return `${parsed.protocol}//${parsed.host}${parsed.pathname}`;
  } catch {
    return (rawUrl.split("?")[0] ?? "").split("#")[0];
  }
}

export function sanitizeHeaders(
  headers?: Record<string, string>,
): Record<string, string> | undefined {
  if (!headers) return undefined;
  const sanitized: Record<string, string> = {};
  for (const [key, value] of Object.entries(headers)) {
    const lower = key.toLowerCase();
    if (ALLOWED_HEADERS.has(lower)) {
      if (lower === "referer") {
        sanitized[key] = sanitizeUrl(value) ?? "";
      } else {
        sanitized[key] = value;
      }
    }
  }
  return sanitized;
}

export function sanitizeTextUrls(text?: string | null): string | undefined {
  if (!text) return text ?? undefined;
  // Replace query strings and fragments in text containing URLs
  return text.replace(/https?:\/\/[^\s?#]+(\?[^\s#]*)?(#[^\s]*)?/gi, (match) => {
    return sanitizeUrl(match) ?? match;
  });
}

export interface SentryBreadcrumbLike {
  data?: {
    url?: string;
    to?: string;
    from?: string;
    [key: string]: unknown;
  };
  message?: string;
  [key: string]: unknown;
}

export interface SentryEventLike {
  request?: {
    url?: string;
    query_string?: unknown;
    data?: unknown;
    cookies?: unknown;
    env?: unknown;
    headers?: Record<string, string>;
    [key: string]: unknown;
  };
  user?: unknown;
  spans?: Array<{
    data?: Record<string, unknown>;
    [key: string]: unknown;
  }>;
  breadcrumbs?: SentryBreadcrumbLike[];
  [key: string]: unknown;
}

/**
 * Scrubber for Sentry error and message events (beforeSend).
 */
export function beforeSendScrubber<T = unknown>(event: T): T {
  if (!event) return event;
  const ev = event as unknown as SentryEventLike;

  // 1. Delete user object entirely (no visitor or staff IP / identity in errors)
  delete ev.user;

  // 2. Scrub request details
  if (ev.request) {
    if (ev.request.url) {
      ev.request.url = sanitizeUrl(ev.request.url);
    }
    delete ev.request.query_string;
    delete ev.request.data;
    delete ev.request.cookies;
    delete ev.request.env;

    if (ev.request.headers) {
      ev.request.headers = sanitizeHeaders(ev.request.headers);
    }
  }

  // 3. Scrub breadcrumbs
  if (Array.isArray(ev.breadcrumbs)) {
    for (const b of ev.breadcrumbs) {
      beforeBreadcrumbScrubber(b);
    }
  }

  return event;
}

/**
 * Scrubber for Sentry performance / transaction events (beforeSendTransaction).
 */
export function beforeSendTransactionScrubber<T = unknown>(event: T): T {
  if (!event) return event;
  const ev = event as unknown as SentryEventLike;

  delete ev.user;

  if (ev.request) {
    if (ev.request.url) {
      ev.request.url = sanitizeUrl(ev.request.url);
    }
    delete ev.request.query_string;
    delete ev.request.data;
    delete ev.request.cookies;
    delete ev.request.env;

    if (ev.request.headers) {
      ev.request.headers = sanitizeHeaders(ev.request.headers);
    }
  }

  // Scrub spans data
  if (Array.isArray(ev.spans)) {
    for (const span of ev.spans) {
      if (span.data) {
        for (const [key, val] of Object.entries(span.data)) {
          if (typeof val === "string") {
            const lowerKey = key.toLowerCase();
            if (lowerKey.includes("query")) {
              span.data[key] = "";
            } else if (
              lowerKey.includes("url") ||
              lowerKey.includes("path") ||
              lowerKey.includes("target")
            ) {
              span.data[key] = sanitizeUrl(val);
            }
          }
        }
      }
    }
  }

  return event;
}

/**
 * Scrubber for Sentry breadcrumbs (beforeBreadcrumb).
 */
export function beforeBreadcrumbScrubber<T = unknown>(breadcrumb: T): T {
  if (!breadcrumb) return breadcrumb;
  const b = breadcrumb as unknown as SentryBreadcrumbLike;

  if (b.data) {
    for (const key of ["url", "to", "from"]) {
      if (typeof b.data[key] === "string") {
        b.data[key] = sanitizeUrl(b.data[key] as string);
      }
    }
  }

  if (typeof b.message === "string") {
    b.message = sanitizeTextUrls(b.message);
  }

  return breadcrumb;
}
