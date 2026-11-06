/**
 * proxy.ts after the L2 security review: internal routes stay unreachable even percent-encoded,
 * an /api call with no client IP from the host is refused, and production enforces the CSP.
 */
import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/lib/public/redirects", () => ({
  findRedirect: async () => null,
  reportHit: async () => undefined,
}));

const { proxy } = await import("../src/proxy");

const event = { waitUntil: () => undefined } as never;

function req(path: string, headers: Record<string, string> = {}): NextRequest {
  return new NextRequest(new URL(path, "https://empirebuildcon.com"), { headers });
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("internal API routes", () => {
  it.each([
    "/api/v1/internal/outbox/drain",
    "/api/v1/internal%2Foutbox/drain",
    "/api/v1/%69nternal/outbox/drain",
    "/api/v1/internal%252Foutbox/drain",
  ])("%s is not found", async (path) => {
    const res = await proxy(req(path), event);
    expect(res.status).toBe(404);
  });

  it("a broken escape is refused", async () => {
    const res = await proxy(req("/api/v1/%E0%A4%A"), event);
    expect(res.status).toBe(400);
  });

  it("a page path with a stray % isn't decoded here", async () => {
    const res = await proxy(req("/offers/50%-off"), event);
    expect(res.status).toBe(200);
  });
});

describe("the visitor's IP on /api calls", () => {
  it("is required on a hosted site with the edge key on", async () => {
    vi.stubEnv("APP_ENV", "production");
    vi.stubEnv("EDGE_PROXY_KEY", "k".repeat(40));
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const res = await proxy(req("/api/v1/public/site"), event);
    expect(res.status).toBe(503);
  });

  it("is passed on when the host gives it", async () => {
    vi.stubEnv("EDGE_PROXY_KEY", "k".repeat(40));
    const res = await proxy(
      req("/api/v1/public/site", { "x-nf-client-connection-ip": "203.0.113.9" }),
      event,
    );
    expect(res.status).toBe(200);
    expect(res.headers.get("x-middleware-request-x-empire-client-ip")).toBe("203.0.113.9");
  });

  it("isn't needed in tests, where no hosting platform adds it", async () => {
    vi.stubEnv("APP_ENV", "test");
    vi.stubEnv("EDGE_PROXY_KEY", "k".repeat(40));
    const res = await proxy(req("/api/v1/public/site"), event);
    expect(res.status).toBe(200);
  });

  it("isn't needed locally (no edge key)", async () => {
    vi.stubEnv("EDGE_PROXY_KEY", "");
    const res = await proxy(req("/api/v1/public/site"), event);
    expect(res.status).toBe(200);
  });
});

describe("Content-Security-Policy", () => {
  it("is enforced in production", async () => {
    vi.stubEnv("APP_ENV", "production");
    vi.stubEnv("CSP_ENFORCE", "");
    const res = await proxy(req("/projects"), event);
    expect(res.headers.get("content-security-policy")).toContain("script-src");
    expect(res.headers.get("content-security-policy-report-only")).toBeNull();
  });

  it("can be switched to report-only in production on purpose", async () => {
    vi.stubEnv("APP_ENV", "production");
    vi.stubEnv("CSP_ENFORCE", "false");
    const res = await proxy(req("/projects"), event);
    expect(res.headers.get("content-security-policy")).toBeNull();
    expect(res.headers.get("content-security-policy-report-only")).toContain("script-src");
  });

  it("only reports on staging until switched on", async () => {
    vi.stubEnv("APP_ENV", "staging");
    vi.stubEnv("CSP_ENFORCE", "");
    const res = await proxy(req("/projects"), event);
    expect(res.headers.get("content-security-policy")).toBeNull();
    expect(res.headers.get("content-security-policy-report-only")).toContain("script-src");
  });
});
