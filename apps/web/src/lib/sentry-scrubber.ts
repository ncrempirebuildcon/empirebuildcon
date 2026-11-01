/**
 * Sentry data scrubber (SECURITY §8, Phase 5 Task 5.2).
 *
 * Implements:
 *   - Drops query strings and fragments from every URL (prevents leaking lead ?q= numbers, tokens).
 *   - Removes request bodies, cookies, and visitor IP addresses.
 *   - Strips URLs in breadcrumbs.
 */

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

export interface SentryEventLike {
  request?: {
    url?: string;
    data?: unknown;
    cookies?: unknown;
    headers?: Record<string, string>;
  };
  user?: {
    ip_address?: string;
    [key: string]: unknown;
  };
  breadcrumbs?: Array<{
    data?: {
      url?: string;
      to?: string;
      from?: string;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  }>;
  [key: string]: unknown;
}

export function beforeSendScrubber<T extends SentryEventLike>(event: T): T {
  if (!event) return event;

  // Drop IP address
  if (event.user && "ip_address" in event.user) {
    delete event.user.ip_address;
  }

  // Scrub request details
  if (event.request) {
    if (event.request.url) {
      event.request.url = sanitizeUrl(event.request.url);
    }
    delete event.request.data;
    delete event.request.cookies;

    if (event.request.headers) {
      const sanitizedHeaders: Record<string, string> = {};
      for (const [key, value] of Object.entries(event.request.headers)) {
        const lower = key.toLowerCase();
        if (
          lower === "cookie" ||
          lower === "x-empire-client-ip" ||
          lower === "x-forwarded-for" ||
          lower === "authorization"
        ) {
          continue;
        }
        sanitizedHeaders[key] = value;
      }
      event.request.headers = sanitizedHeaders;
    }
  }

  // Scrub breadcrumb URLs
  if (Array.isArray(event.breadcrumbs)) {
    for (const b of event.breadcrumbs) {
      if (b.data?.url) {
        b.data.url = sanitizeUrl(b.data.url);
      }
      if (b.data?.to) {
        b.data.to = sanitizeUrl(b.data.to);
      }
      if (b.data?.from) {
        b.data.from = sanitizeUrl(b.data.from);
      }
    }
  }

  return event;
}
