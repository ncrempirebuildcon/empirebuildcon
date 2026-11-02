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
  // Replace query strings and fragments in text containing full URLs
  let res = text.replace(/https?:\/\/[^\s?#]+(\?[^\s#]*)?(#[^\s]*)?/gi, (match) => {
    return sanitizeUrl(match) ?? match;
  });
  // Also replace query strings and fragments in path-like strings e.g. "GET /admin/leads?q=..."
  res = res.replace(/(\/[a-zA-Z0-9_\-./]+)(\?[^\s#]*)?(#[^\s]*)?/gi, "$1");
  return res;
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
  transaction?: string;
  contexts?: {
    trace?: {
      data?: Record<string, unknown>;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
  spans?: Array<{
    description?: string;
    data?: Record<string, unknown>;
    [key: string]: unknown;
  }>;
  breadcrumbs?: SentryBreadcrumbLike[];
  [key: string]: unknown;
}

/**
 * Scrubs span attributes (used on root span `contexts.trace.data` and `spans[].data`).
 *
 * Drops:
 *   - `http.request.header.*`, `http.response.header.*` (e.g. x-forwarded-for, x-empire-client-ip)
 *   - `client.*`, `network.peer.*`, `user.*`, `http.request.body.*` (e.g. visitor IP address, body)
 *   - Empties any `*.query` or `*.fragment`
 *   - Sanitizes URLs and paths (dropping query strings and fragments)
 */
export function scrubSpanData(data?: Record<string, unknown>): void {
  if (!data) return;
  for (const key of Object.keys(data)) {
    const lowerKey = key.toLowerCase();
    // Drop sensitive headers, client IPs, peer info, user info, bodies
    if (
      lowerKey.startsWith("http.request.header.") ||
      lowerKey.startsWith("http.response.header.") ||
      lowerKey.startsWith("client.") ||
      lowerKey.startsWith("network.peer.") ||
      lowerKey.startsWith("user.") ||
      lowerKey.startsWith("http.request.body.")
    ) {
      delete data[key];
      continue;
    }

    // Empty query / fragment keys
    if (lowerKey.endsWith(".query") || lowerKey.endsWith(".fragment") || lowerKey === "query") {
      data[key] = "";
      continue;
    }

    // Sanitize URLs and targets
    if (
      lowerKey.startsWith("url.") ||
      lowerKey === "http.url" ||
      lowerKey === "http.target" ||
      lowerKey.includes("url") ||
      lowerKey.includes("path") ||
      lowerKey.includes("target")
    ) {
      const val = data[key];
      if (typeof val === "string") {
        data[key] = sanitizeUrl(val);
      }
    }
  }
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

  // 3. Scrub root span trace data if present
  if (ev.contexts?.trace?.data) {
    scrubSpanData(ev.contexts.trace.data);
  }

  // 4. Scrub breadcrumbs
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

  if (ev.transaction && typeof ev.transaction === "string") {
    ev.transaction = sanitizeTextUrls(ev.transaction);
  }

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

  // Root span data in contexts.trace.data (M5, R2-M2)
  if (ev.contexts?.trace?.data) {
    scrubSpanData(ev.contexts.trace.data);
  }

  // Child spans data and description (M5, R2-M2)
  if (Array.isArray(ev.spans)) {
    for (const span of ev.spans) {
      if (span.data) {
        scrubSpanData(span.data);
      }
      if (span.description && typeof span.description === "string") {
        span.description = sanitizeTextUrls(span.description);
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
