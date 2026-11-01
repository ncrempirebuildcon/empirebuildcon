import { describe, expect, it } from "vitest";
import {
  beforeBreadcrumbScrubber,
  beforeSendScrubber,
  beforeSendTransactionScrubber,
  sanitizeUrl,
} from "../src/lib/sentry-scrubber";

describe("Sentry Scrubber (M5)", () => {
  it("drops query parameters and fragments from URLs", () => {
    expect(sanitizeUrl("https://example.com/admin/leads?q=9876543210#row-1")).toBe(
      "https://example.com/admin/leads",
    );
    expect(sanitizeUrl("/admin/leads?status=new&q=9876543210")).toBe("/admin/leads");
    expect(sanitizeUrl("https://example.com/admin/reset?token=secret123")).toBe(
      "https://example.com/admin/reset",
    );
  });

  it("scrubs lead search queries, drops query_string, and deletes user entirely in beforeSend", () => {
    const rawEvent = {
      request: {
        url: "https://example.com/admin/leads?q=9876543210",
        query_string: "q=9876543210",
        data: { name: "Secret Lead" },
        cookies: { session: "secret-cookie" },
        env: { EDGE_PROXY_KEY: "secret-key" },
        headers: {
          "user-agent": "Mozilla/5.0",
          "accept-language": "en-US",
          referer: "https://example.com/admin/leads?q=9876543210",
          cookie: "session=123",
          authorization: "Bearer secret",
          "x-empire-edge-key": "super-secret-key",
          "x-empire-client-ip": "203.0.113.195",
          "x-nf-client-connection-ip": "203.0.113.195",
          "x-forwarded-for": "203.0.113.195",
        },
      },
      user: {
        id: "staff-123",
        ip_address: "203.0.113.195",
        email: "staff@example.com",
      },
    };

    const scrubbed = beforeSendScrubber(rawEvent);

    // URL scrubbed
    expect(scrubbed.request?.url).toBe("https://example.com/admin/leads");
    // query_string, data, cookies, env removed
    expect(scrubbed.request?.query_string).toBeUndefined();
    expect(scrubbed.request?.data).toBeUndefined();
    expect(scrubbed.request?.cookies).toBeUndefined();
    expect(scrubbed.request?.env).toBeUndefined();

    // User deleted entirely
    expect(scrubbed.user).toBeUndefined();

    // Headers allowlisted: edge key, client IP, cookies, auth stripped; referer scrubbed
    const headers = scrubbed.request?.headers ?? {};
    expect(headers["user-agent"]).toBe("Mozilla/5.0");
    expect(headers["accept-language"]).toBe("en-US");
    expect(headers.referer).toBe("https://example.com/admin/leads");
    expect(headers.cookie).toBeUndefined();
    expect(headers.authorization).toBeUndefined();
    expect(headers["x-empire-edge-key"]).toBeUndefined();
    expect(headers["x-empire-client-ip"]).toBeUndefined();
    expect(headers["x-nf-client-connection-ip"]).toBeUndefined();
    expect(headers["x-forwarded-for"]).toBeUndefined();
  });

  it("scrubs transaction events, deleting query_string and span URLs in beforeSendTransaction", () => {
    const rawTx = {
      request: {
        url: "https://example.com/admin/leads?q=9876543210",
        query_string: "q=9876543210",
      },
      user: { id: "user-1", ip_address: "1.2.3.4" },
      spans: [
        {
          data: {
            "http.url": "https://example.com/api/v1/leads?q=9876543210",
            "http.query": "?q=9876543210",
            description: "fetch lead",
          },
        },
      ],
    };

    const scrubbed = beforeSendTransactionScrubber(rawTx);
    expect(scrubbed.request?.url).toBe("https://example.com/admin/leads");
    expect(scrubbed.request?.query_string).toBeUndefined();
    expect(scrubbed.user).toBeUndefined();

    const spanData = (scrubbed.spans?.[0]?.data ?? {}) as Record<string, unknown>;
    expect(spanData["http.url"]).toBe("https://example.com/api/v1/leads");
    expect(spanData["http.query"]).toBe("");
  });

  it("scrubs URLs from breadcrumb data and breadcrumb message", () => {
    const rawBreadcrumb = {
      category: "navigation",
      data: {
        url: "https://example.com/admin/leads?q=9876543210#card",
        to: "/admin/projects?tab=pricing&q=secret#top",
      },
      message: "Navigated to https://example.com/admin/leads?q=9876543210 from dashboard",
    };

    const scrubbed = beforeBreadcrumbScrubber(rawBreadcrumb);
    expect(scrubbed.data?.url).toBe("https://example.com/admin/leads");
    expect(scrubbed.data?.to).toBe("/admin/projects");
    expect(scrubbed.message).toBe("Navigated to https://example.com/admin/leads from dashboard");
  });
});
