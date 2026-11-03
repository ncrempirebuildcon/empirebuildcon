import { afterEach, describe, expect, it, vi } from "vitest";
import {
  findRedirect,
  hitSignature,
  isRedirectable,
  locationFor,
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
  { from_path: "/caf%C3%A9", to_path: "/about", status_code: 308 },
  { from_path: "/a%2Fb", to_path: "/about", status_code: 308 },
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
  resetRedirectCache();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

// The same vector is checked by the API (tests/test_redirect_hits.py), so the two never drift.
export const SHARED_VECTOR = {
  secret: "shared-test-secret",
  ts: 1700000000000,
  body: '{"from_path":"/old-offer"}',
  signature: "84c44ffcdc10e4cd77cb2e6f291ae9a3e482b9bfa0ddad80a262a16449456afb",
};

describe("redirect helpers", () => {
  it("normalises paths like the API", () => {
    expect(normalisePath("/a/")).toBe("/a");
    expect(normalisePath("/")).toBe("/");
    expect(normalisePath("/%C3%A9v%C3%A8nement")).toBe("/évènement");
    expect(normalisePath("/%E0%A4%A")).toBe("/%E0%A4%A");
    // An escaped slash stays escaped, so "/a%2Fb" never matches the redirect from "/a/b".
    expect(normalisePath("/a%2Fb")).toBe("/a%2Fb");
    expect(normalisePath("/a%2fb")).toBe("/a%2Fb");
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

describe("locationFor", () => {
  it("puts the visitor's query before the target's fragment and drops _rsc", () => {
    expect(locationFor("/projects/x#prices", "?utm_source=fb")).toBe(
      "/projects/x?utm_source=fb#prices",
    );
    expect(locationFor("/contact", "?_rsc=abc&utm_source=fb")).toBe("/contact?utm_source=fb");
    expect(locationFor("/contact", "?_rsc=abc")).toBe("/contact");
    expect(locationFor("/x?tab=1#a", "?utm_source=fb")).toBe("/x?tab=1#a");
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
    // An address staff typed %-encoded matches the visitor's, encoded or not.
    expect((await findRedirect("/caf%C3%A9", ""))?.location).toBe("/about");
    expect((await findRedirect("/café", ""))?.location).toBe("/about");
    // An escaped slash is its own address.
    expect(await findRedirect("/a/b", "")).toBeNull();
    expect((await findRedirect("/a%2Fb", ""))?.location).toBe("/about");
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

  it("keeps the last list when the API goes down, and never waits for a refresh", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    const fetchMock = mockApi();
    expect(await findRedirect("/old-offer", "")).not.toBeNull();
    vi.setSystemTime(Date.now() + 61_000);
    fetchMock.mockImplementation(async () => new Response("", { status: 503 }));
    // Stale: answered from the old list at once, while a refresh runs (and fails).
    expect(await findRedirect("/old-offer", "")).not.toBeNull();
    await resetRedirectCacheKeepingList();
    expect(await findRedirect("/old-offer", "")).not.toBeNull();
    // After a failure the next try waits 10 seconds.
    const calls = fetchMock.mock.calls.length;
    await findRedirect("/old-offer", "");
    expect(fetchMock.mock.calls.length).toBe(calls);
  });

  it("waits at most 800 ms for a process's first list", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => undefined)),
    );
    const started = Date.now();
    expect(await findRedirect("/old-offer", "")).toBeNull();
    expect(Date.now() - started).toBeLessThan(1_400);
  });
});

/** Lets a background refresh finish without forgetting the list. */
async function resetRedirectCacheKeepingList(): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
}

describe("reportHit", () => {
  it("matches the API's signature for the shared vector", () => {
    const v = SHARED_VECTOR;
    expect(hitSignature(v.secret, v.ts, v.body)).toBe(v.signature);
  });

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
