import { afterEach, describe, expect, it, vi } from "vitest";
import {
  beforeBreadcrumbScrubber,
  beforeSendScrubber,
  beforeSendTransactionScrubber,
  sanitizeUrl,
} from "../src/lib/sentry-scrubber";

const mockInit = vi.fn();
vi.mock("@sentry/nextjs", () => ({
  init: (...args: unknown[]) => mockInit(...args),
}));

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

  it("scrubs transaction events with root-span trace data, deleting query_string, IP and headers (M5, R2-M2)", () => {
    const sdkTransaction = {
      type: "transaction",
      transaction: "GET /admin/leads?q=9876543210",
      contexts: {
        trace: {
          span_id: "1234567890abcdef",
          trace_id: "abcdef1234567890abcdef1234567890",
          op: "http.server",
          data: {
            "url.full": "http://localhost:3000/admin/leads?q=9876543210",
            "url.path": "/admin/leads",
            "url.query": "q=9876543210",
            "http.target": "/admin/leads?q=9876543210",
            "client.address": "203.0.113.195",
            "network.peer.address": "127.0.0.1",
            "user.ip_address": "203.0.113.195",
            "http.request.header.x-forwarded-for": "203.0.113.195",
            "http.request.header.x-nf-client-connection-ip": "203.0.113.195",
            "http.request.header.x-empire-client-ip": "203.0.113.195",
            "http.request.header.x-empire-edge-key": "secret-edge-key-here",
            "http.request.header.user-agent": "Mozilla/5.0",
            "http.request.body.data": "secret body",
          },
        },
      },
      request: {
        url: "http://localhost:3000/admin/leads?q=9876543210",
        query_string: "q=9876543210",
        headers: {
          "x-forwarded-for": "203.0.113.195",
          "x-nf-client-connection-ip": "203.0.113.195",
          "x-empire-client-ip": "203.0.113.195",
          "x-empire-edge-key": "secret-edge-key-here",
          "user-agent": "Mozilla/5.0",
        },
      },
      user: {
        ip_address: "203.0.113.195",
      },
      spans: [
        {
          description: "GET /api/v1/admin/leads?q=9876543210",
          op: "http.client",
          data: {
            "url.full": "http://localhost:8000/api/v1/admin/leads?q=9876543210",
            "url.query": "q=9876543210",
            "http.request.header.x-empire-edge-key": "secret-edge-key-here",
            "http.request.header.x-empire-client-ip": "203.0.113.195",
          },
        },
      ],
    };

    const scrubbed = beforeSendTransactionScrubber(sdkTransaction);

    // Event-level fields
    expect(scrubbed.transaction).toBe("GET /admin/leads");
    expect(scrubbed.user).toBeUndefined();
    expect(scrubbed.request?.url).toBe("http://localhost:3000/admin/leads");
    expect(scrubbed.request?.query_string).toBeUndefined();

    // Headers allowlisted on request
    const reqHeaders = scrubbed.request?.headers ?? {};
    expect(reqHeaders["x-forwarded-for"]).toBeUndefined();
    expect(reqHeaders["x-empire-edge-key"]).toBeUndefined();
    expect(reqHeaders["user-agent"]).toBe("Mozilla/5.0");

    // Root span attributes scrubbed (R2-M2)
    const traceData = (scrubbed.contexts?.trace?.data ?? {}) as Record<string, unknown>;
    expect(traceData["url.full"]).toBe("http://localhost:3000/admin/leads");
    expect(traceData["url.query"]).toBe("");
    expect(traceData["http.target"]).toBe("/admin/leads");
    expect(traceData["client.address"]).toBeUndefined();
    expect(traceData["network.peer.address"]).toBeUndefined();
    expect(traceData["user.ip_address"]).toBeUndefined();
    expect(traceData["http.request.header.x-forwarded-for"]).toBeUndefined();
    expect(traceData["http.request.header.x-nf-client-connection-ip"]).toBeUndefined();
    expect(traceData["http.request.header.x-empire-client-ip"]).toBeUndefined();
    expect(traceData["http.request.header.x-empire-edge-key"]).toBeUndefined();
    expect(traceData["http.request.body.data"]).toBeUndefined();

    // Child span scrubbed
    const childSpan = scrubbed.spans?.[0];
    expect(childSpan?.description).toBe("GET /api/v1/admin/leads");
    const childSpanData = (childSpan?.data ?? {}) as Record<string, unknown>;
    expect(childSpanData["url.full"]).toBe("http://localhost:8000/api/v1/admin/leads");
    expect(childSpanData["url.query"]).toBe("");
    expect(childSpanData["http.request.header.x-empire-edge-key"]).toBeUndefined();
    expect(childSpanData["http.request.header.x-empire-client-ip"]).toBeUndefined();
  });

  describe("Sentry init configurations (R2-M2, S-4)", () => {
    const originalDsn = process.env.SENTRY_DSN;
    const originalPublicDsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

    afterEach(() => {
      if (originalDsn !== undefined) {
        process.env.SENTRY_DSN = originalDsn;
      } else {
        delete process.env.SENTRY_DSN;
      }
      if (originalPublicDsn !== undefined) {
        process.env.NEXT_PUBLIC_SENTRY_DSN = originalPublicDsn;
      } else {
        delete process.env.NEXT_PUBLIC_SENTRY_DSN;
      }
      mockInit.mockClear();
    });

    it("server config initializes Sentry when DSN is present and disables when absent", async () => {
      // Unset DSN
      delete process.env.SENTRY_DSN;
      delete process.env.NEXT_PUBLIC_SENTRY_DSN;
      vi.resetModules();
      await import("../sentry.server.config");
      expect(mockInit).toHaveBeenLastCalledWith(
        expect.objectContaining({
          enabled: false,
          dsn: "",
          dataCollection: {
            userInfo: false,
            cookies: false,
            httpHeaders: false,
            httpBodies: [],
            urlQueryParams: false,
            databaseQueryData: false,
          },
        }),
      );

      // Set DSN
      process.env.SENTRY_DSN = "https://public@example.com/1";
      vi.resetModules();
      await import("../sentry.server.config");
      expect(mockInit).toHaveBeenLastCalledWith(
        expect.objectContaining({
          enabled: true,
          dsn: "https://public@example.com/1",
          dataCollection: {
            userInfo: false,
            cookies: false,
            httpHeaders: false,
            httpBodies: [],
            urlQueryParams: false,
            databaseQueryData: false,
          },
          beforeSend: expect.any(Function),
          beforeSendTransaction: expect.any(Function),
          beforeBreadcrumb: expect.any(Function),
        }),
      );
    });

    it("edge config initializes Sentry when DSN is present and disables when absent", async () => {
      // Unset DSN
      delete process.env.SENTRY_DSN;
      delete process.env.NEXT_PUBLIC_SENTRY_DSN;
      vi.resetModules();
      await import("../sentry.edge.config");
      expect(mockInit).toHaveBeenLastCalledWith(
        expect.objectContaining({
          enabled: false,
          dsn: "",
        }),
      );

      // Set DSN via NEXT_PUBLIC_SENTRY_DSN
      process.env.NEXT_PUBLIC_SENTRY_DSN = "https://edge@example.com/2";
      vi.resetModules();
      await import("../sentry.edge.config");
      expect(mockInit).toHaveBeenLastCalledWith(
        expect.objectContaining({
          enabled: true,
          dsn: "https://edge@example.com/2",
        }),
      );
    });

    it("client config initializes Sentry when NEXT_PUBLIC_SENTRY_DSN is present and disables when absent", async () => {
      // Unset DSN
      delete process.env.NEXT_PUBLIC_SENTRY_DSN;
      vi.resetModules();
      await import("../sentry.client.config");
      expect(mockInit).toHaveBeenLastCalledWith(
        expect.objectContaining({
          enabled: false,
          dsn: "",
        }),
      );

      // Set DSN
      process.env.NEXT_PUBLIC_SENTRY_DSN = "https://client@example.com/3";
      vi.resetModules();
      await import("../sentry.client.config");
      expect(mockInit).toHaveBeenLastCalledWith(
        expect.objectContaining({
          enabled: true,
          dsn: "https://client@example.com/3",
          dataCollection: {
            userInfo: false,
            cookies: false,
            httpHeaders: false,
            httpBodies: [],
            urlQueryParams: false,
            databaseQueryData: false,
          },
        }),
      );
    });
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
