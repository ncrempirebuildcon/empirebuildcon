import { afterEach, describe, expect, it, vi } from "vitest";

// The data layer is server-only; in Node tests the marker module is a no-op.
vi.mock("server-only", () => ({}));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

import { fetchPublicPost, fetchPublicProject, fetchPublicSite } from "../src/lib/public/api";

type Init = RequestInit & { next?: { tags?: string[]; revalidate?: number } };

function stubFetch(body: unknown, status = 200) {
  const calls: { input: unknown; init?: Init }[] = [];
  vi.stubGlobal("fetch", (input: unknown, init?: Init) => {
    calls.push({ input, init });
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      }),
    );
  });
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("public data layer reaches the Next.js data cache with its tags", () => {
  // Regression: the tags were given to openapi-fetch, which dropped `next` when it built the
  // Request, so revalidation by tag never cleared anything.
  it("tags a project read with the project's own tag and the safety revalidate", async () => {
    const calls = stubFetch({ slug: "aurum" });
    await fetchPublicProject("aurum");
    expect(calls).toHaveLength(1);
    expect(calls[0]?.init?.cache).toBe("force-cache");
    expect(calls[0]?.init?.next).toEqual({
      tags: ["projects", "project:aurum", "content"],
      revalidate: 3600,
    });
    expect(calls[0]?.init?.signal).toBeInstanceOf(AbortSignal);
  });

  it("tags the site settings read with `site`", async () => {
    const calls = stubFetch({ company: {} });
    await fetchPublicSite();
    expect(calls[0]?.init?.next?.tags).toEqual(["site", "content"]);
  });

  it("tags a post read with `post:<slug>` and turns a 404 into notFound()", async () => {
    const calls = stubFetch({ title: "Not found", status: 404 }, 404);
    await expect(fetchPublicPost("missing")).rejects.toThrow("NEXT_NOT_FOUND");
    expect(calls[0]?.init?.next?.tags).toEqual(["posts", "post:missing", "content"]);
  });
});
