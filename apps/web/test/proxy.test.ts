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

describe("tracking hosts in the CSP (task 6.3, D-058)", () => {
  function policy(res: Response): string {
    return (
      res.headers.get("content-security-policy") ??
      res.headers.get("content-security-policy-report-only") ??
      ""
    );
  }
  function directive(csp: string, name: string): string {
    return (
      csp
        .split(";")
        .map((d) => d.trim())
        .find((d) => d.startsWith(`${name} `)) ?? ""
    );
  }

  it("adds no ad or analytics host by default (the launch CSP)", async () => {
    vi.stubEnv("TRACKING_CSP", "");
    const csp = policy(await proxy(req("/projects"), event));
    expect(csp).not.toContain("googletagmanager");
    expect(csp).not.toContain("facebook");
    expect(directive(csp, "frame-src")).toBe("");
  });

  it("opens only Google's hosts for TRACKING_CSP=google", async () => {
    vi.stubEnv("TRACKING_CSP", "google");
    const csp = policy(await proxy(req("/projects"), event));
    expect(directive(csp, "script-src")).toContain("https://www.googletagmanager.com");
    expect(directive(csp, "connect-src")).toContain("https://*.google-analytics.com");
    expect(directive(csp, "frame-src")).toBe("frame-src 'self' https://www.googletagmanager.com");
    expect(csp).not.toContain("facebook");
  });

  it("never opens them on the CMS, where no tag runs", async () => {
    vi.stubEnv("TRACKING_CSP", "google,meta");
    for (const path of ["/admin", "/admin/leads"]) {
      const csp = policy(await proxy(req(path), event));
      expect(csp, path).not.toContain("googletagmanager");
      expect(csp, path).not.toContain("facebook");
    }
  });

  it("opens Meta's hosts for TRACKING_CSP=meta, and ignores unknown words", async () => {
    vi.stubEnv("TRACKING_CSP", " Meta , tiktok ");
    const csp = policy(await proxy(req("/projects"), event));
    expect(directive(csp, "script-src")).toContain("https://connect.facebook.net");
    expect(directive(csp, "img-src")).toContain("https://www.facebook.com");
    expect(csp).not.toContain("googletagmanager");
    expect(csp).not.toContain("tiktok");
  });
});
