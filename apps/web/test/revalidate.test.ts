import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  _clearReplayCache,
  computeSignature,
  processRevalidate,
  revalidateHandler,
  SIGNATURE_HEADER,
  TIMESTAMP_HEADER,
} from "../src/lib/public/revalidate";

// Mock next/cache so we can assert revalidateTag is called
const mockRevalidateTag = vi.fn();
vi.mock("next/cache", () => ({
  revalidateTag: (...args: unknown[]) => mockRevalidateTag(...args),
}));

const SECRET = "test-secret-that-is-at-least-thirty-two-bytes-long";
const WRONG_SECRET = "wrong-secret-that-is-also-at-least-thirty-two-bytes-long";

describe("processRevalidate and revalidateHandler", () => {
  const originalSecret = process.env.REVALIDATE_SECRET;

  beforeEach(() => {
    process.env.REVALIDATE_SECRET = SECRET;
    _clearReplayCache();
    mockRevalidateTag.mockClear();
  });

  afterEach(() => {
    if (originalSecret !== undefined) {
      process.env.REVALIDATE_SECRET = originalSecret;
    } else {
      delete process.env.REVALIDATE_SECRET;
    }
  });

  it("matches the Python API shared test vector (N8)", () => {
    const sharedSecret = "test-secret-shared-vector-48-chars-long-example";
    const timestamp = 1793557400000;
    const body = '{"tags":["site","projects"]}';
    const expected = "1aa1e51fbe111e5f91493b9e78089e7e29e572fbacce7d4d1da1079ec9d6e6ed";

    expect(computeSignature(sharedSecret, timestamp, body)).toBe(expected);
  });

  it("accepts a valid signed POST request via processRevalidate and calls revalidateTag for each tag", async () => {
    const now = Date.now();
    const body = JSON.stringify({ tags: ["site", "project:alpha"] });
    const signature = computeSignature(SECRET, now, body);

    const request = new Request("https://example.com/_internal/revalidate", {
      method: "POST",
      headers: {
        [SIGNATURE_HEADER]: signature,
        [TIMESTAMP_HEADER]: String(now),
        "content-type": "application/json",
      },
      body,
    });

    const result = await processRevalidate(request, { secret: SECRET, now });
    expect(result.ok).toBe(true);
    expect(result.status).toBe(200);
    expect(result.tags).toEqual(["site", "project:alpha"]);
    expect(mockRevalidateTag).toHaveBeenCalledTimes(2);
    expect(mockRevalidateTag).toHaveBeenCalledWith("site", { expire: 0 });
    expect(mockRevalidateTag).toHaveBeenCalledWith("project:alpha", { expire: 0 });
  });

  it("accepts a valid signed request via revalidateHandler reading secret from env", async () => {
    const now = Date.now();
    const body = JSON.stringify({ tags: ["site", "content"] });
    const signature = computeSignature(SECRET, now, body);

    const request = new Request("https://example.com/_internal/revalidate", {
      method: "POST",
      headers: {
        [SIGNATURE_HEADER]: signature,
        [TIMESTAMP_HEADER]: String(now),
        "content-type": "application/json",
      },
      body,
    });

    const response = await revalidateHandler(request);
    expect(response.status).toBe(200);
    const json = (await response.json()) as { revalidated: boolean; tags: string[] };
    expect(json.revalidated).toBe(true);
    expect(json.tags).toEqual(["site", "content"]);
    expect(mockRevalidateTag).toHaveBeenCalledTimes(2);
  });

  it("refuses unsigned request with 401 and empty body (S-N2)", async () => {
    const request = new Request("https://example.com/_internal/revalidate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ tags: ["site"] }),
    });

    const response = await revalidateHandler(request);
    expect(response.status).toBe(401);
    expect(await response.text()).toBe("");
    expect(mockRevalidateTag).not.toHaveBeenCalled();
  });

  it("refuses well-formed but invalid signature with 401 and empty body (S-N2)", async () => {
    const now = Date.now();
    const body = JSON.stringify({ tags: ["site"] });
    // Sign with a different secret to produce a well-formed 64-hex signature that fails timingSafeEqual
    const wrongSignature = computeSignature(WRONG_SECRET, now, body);

    const request = new Request("https://example.com/_internal/revalidate", {
      method: "POST",
      headers: {
        [SIGNATURE_HEADER]: wrongSignature,
        [TIMESTAMP_HEADER]: String(now),
        "content-type": "application/json",
      },
      body,
    });

    const response = await revalidateHandler(request);
    expect(response.status).toBe(401);
    expect(await response.text()).toBe("");
    expect(mockRevalidateTag).not.toHaveBeenCalled();
  });

  it("refuses missing or empty tags with 401 and empty body (S-N2)", async () => {
    const now = Date.now();
    const emptyBody = JSON.stringify({ tags: [] });
    const signature = computeSignature(SECRET, now, emptyBody);

    const request = new Request("https://example.com/_internal/revalidate", {
      method: "POST",
      headers: {
        [SIGNATURE_HEADER]: signature,
        [TIMESTAMP_HEADER]: String(now),
        "content-type": "application/json",
      },
      body: emptyBody,
    });

    const response = await revalidateHandler(request);
    expect(response.status).toBe(401);
    expect(await response.text()).toBe("");
    expect(mockRevalidateTag).not.toHaveBeenCalled();
  });

  it("rejects suffixed or non-hex signatures (M3)", async () => {
    const now = Date.now();
    const body = JSON.stringify({ tags: ["site"] });
    const validSignature = computeSignature(SECRET, now, body);

    // Suffixed with 'zz'
    const suffixedRequest = new Request("https://example.com/_internal/revalidate", {
      method: "POST",
      headers: {
        [SIGNATURE_HEADER]: `${validSignature}zz`,
        [TIMESTAMP_HEADER]: String(now),
      },
      body,
    });
    const suffixedResult = await processRevalidate(suffixedRequest, { secret: SECRET, now });
    expect(suffixedResult.ok).toBe(false);
    expect(suffixedResult.status).toBe(401);

    // Suffixed with an odd nibble 'a' (65 chars total)
    const oddRequest = new Request("https://example.com/_internal/revalidate", {
      method: "POST",
      headers: {
        [SIGNATURE_HEADER]: `${validSignature}a`,
        [TIMESTAMP_HEADER]: String(now),
      },
      body,
    });
    const oddResult = await processRevalidate(oddRequest, { secret: SECRET, now });
    expect(oddResult.ok).toBe(false);
    expect(oddResult.status).toBe(401);
  });

  it("rejects replayed requests within the window", async () => {
    const now = Date.now();
    const body = JSON.stringify({ tags: ["site"] });
    const signature = computeSignature(SECRET, now, body);

    const makeReq = () =>
      new Request("https://example.com/_internal/revalidate", {
        method: "POST",
        headers: {
          [SIGNATURE_HEADER]: signature,
          [TIMESTAMP_HEADER]: String(now),
        },
        body,
      });

    const firstResponse = await revalidateHandler(makeReq());
    expect(firstResponse.status).toBe(200);

    const replayResponse = await revalidateHandler(makeReq());
    expect(replayResponse.status).toBe(401);
    expect(await replayResponse.text()).toBe("");
  });

  it("rejects timestamps outside the 5-minute freshness window", async () => {
    const now = Date.now();
    const staleTime = now - 6 * 60 * 1000; // 6 minutes ago
    const body = JSON.stringify({ tags: ["site"] });
    const signature = computeSignature(SECRET, staleTime, body);

    const request = new Request("https://example.com/_internal/revalidate", {
      method: "POST",
      headers: {
        [SIGNATURE_HEADER]: signature,
        [TIMESTAMP_HEADER]: String(staleTime),
      },
      body,
    });

    const response = await revalidateHandler(request);
    expect(response.status).toBe(401);
    expect(await response.text()).toBe("");
    expect(mockRevalidateTag).not.toHaveBeenCalled();
  });

  it("rejects oversized request bodies exceeding 16 KB (N2)", async () => {
    const now = Date.now();
    const hugeBody = JSON.stringify({ tags: ["site"], filler: "x".repeat(20 * 1024) });
    const signature = computeSignature(SECRET, now, hugeBody);

    const request = new Request("https://example.com/_internal/revalidate", {
      method: "POST",
      headers: {
        [SIGNATURE_HEADER]: signature,
        [TIMESTAMP_HEADER]: String(now),
        "content-length": String(hugeBody.length),
      },
      body: hugeBody,
    });

    const result = await processRevalidate(request, { secret: SECRET, now });
    expect(result.ok).toBe(false);
    expect(result.status).toBe(401);
  });

  it("rejects non-POST methods with 405", async () => {
    const request = new Request("https://example.com/_internal/revalidate", { method: "GET" });
    const result = await processRevalidate(request, { secret: SECRET });
    expect(result.status).toBe(405);
  });
});
