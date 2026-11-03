import { afterEach, describe, expect, it, vi } from "vitest";
import {
  findRedirect,
  hitSignature,
  isRedirectable,
  normalisePath,
  reportHit,
  resetRedirectCache,
  safeTarget,
} from "../src/lib/public/redirects";

const rows = [
  { from_path: "/old-offer", to_path: "/contact", status_code: 308 },
  { from_path: "/old-tower", to_path: "/projects/x?tab=prices", status_code: 301 },
  { from_path: "/évènement", to_path: "/about", status_code: 308 },
  { from_path: "/evil", to_path: "//evil.example", status_code: 308 },
];

function mockApi(ok = true) {
  const fetchMock = vi.fn(async (url: string) => {
    if (url.endsWith("/api/v1/public/redirects")) {
      return ok ? new Response(JSON.stringify(rows)) : new Response("", { status: 503 });
    }
    return new Response(null, { status: 204 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  resetRedirectCache();
});

describe("redirect helpers", () => {
  it("normalises paths like the API", () => {
    expect(normalisePath("/a/")).toBe("/a");
    expect(normalisePath("/")).toBe("/");
    expect(normalisePath("/%C3%A9v%C3%A8nement")).toBe("/évènement");
    expect(normalisePath("/%E0%A4%A")).toBe("/%E0%A4%A");
  });

  it("never sends a visitor to another host", () => {
    expect(safeTarget("/contact")).toBe("/contact");
    expect(safeTarget("//evil.example")).toBeNull();
    expect(safeTarget("/\\evil.example")).toBeNull();
    expect(safeTarget("https://evil.example")).toBeNull();
  });

  it("never redirects the home page, the CMS, the API or the site's own files", () => {
    for (const p of ["/", "/admin", "/admin/leads", "/API/v1/x", "/_next/x", "/brand/logo.svg"]) {
      expect(isRedirectable(p), p).toBe(false);
    }
    expect(isRedirectable("/old-offer")).toBe(true);
  });
});

describe("findRedirect", () => {
  it("matches the path, keeps the visitor's query unless the target has one", async () => {
    mockApi();
    expect((await findRedirect("/old-offer/", "?utm_source=x"))?.location).toBe(
      "/contact?utm_source=x",
    );
    const tower = await findRedirect("/old-tower", "?utm_source=x");
    expect(tower?.location).toBe("/projects/x?tab=prices");
    expect(tower?.redirect.status_code).toBe(301);
    expect((await findRedirect("/%C3%A9v%C3%A8nement", ""))?.location).toBe("/about");
    expect(await findRedirect("/evil", "")).toBeNull();
    expect(await findRedirect("/Old-Offer", "")).toBeNull();
  });

  it("asks the API once a minute, not on every page", async () => {
    const fetchMock = mockApi();
    await findRedirect("/old-offer", "");
    await findRedirect("/nothing", "");
    await Promise.all([findRedirect("/a", ""), findRedirect("/b", "")]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("serves pages as usual when the API can't be reached", async () => {
    mockApi(false);
    expect(await findRedirect("/old-offer", "")).toBeNull();
  });
});

describe("reportHit", () => {
  it("signs the hit with the shared secret and a redirect-hit prefix", async () => {
    vi.stubEnv("REVALIDATE_SECRET", "s3cret");
    const fetchMock = mockApi();
    await reportHit("/old-offer");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/api\/v1\/internal\/redirects\/hit$/);
    const headers = init.headers as Record<string, string>;
    const ts = Number(headers["x-redirect-hit-timestamp"]);
    expect(headers["x-redirect-hit-signature"]).toBe(
      hitSignature("s3cret", ts, JSON.stringify({ from_path: "/old-offer" })),
    );
  });

  it("sends nothing without the secret and never throws", async () => {
    vi.stubEnv("REVALIDATE_SECRET", "");
    const fetchMock = mockApi();
    await reportHit("/old-offer");
    expect(fetchMock).not.toHaveBeenCalled();
    vi.stubEnv("REVALIDATE_SECRET", "x");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    await expect(reportHit("/old-offer")).resolves.toBeUndefined();
  });
});
