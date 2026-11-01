import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  _clearReplayCache,
  computeSignature,
  processRevalidate,
  SIGNATURE_HEADER,
  TIMESTAMP_HEADER,
  LEGACY_SIGNATURE_HEADER,
  LEGACY_TIMESTAMP_HEADER,
} from "../src/lib/public/revalidate";

// Mock next/cache so we can assert revalidateTag is called
const mockRevalidateTag = vi.fn();
vi.mock("next/cache", () => ({
  revalidateTag: (...args: unknown[]) => mockRevalidateTag(...args),
}));

const SECRET = "test-secret-that-is-at-least-thirty-two-bytes-long";

describe("processRevalidate", () => {
  beforeEach(() => {
    _clearReplayCache();
    mockRevalidateTag.mockClear();
  });

  it("matches the Python API shared test vector (N8)", () => {
    const sharedSecret = "test-secret-shared-vector-48-chars-long-example";
    const timestamp = 1793557400000;
    const body = '{"tags":["site","projects"]}';
    const expected = "1aa1e51fbe111e5f91493b9e78089e7e29e572fbacce7d4d1da1079ec9d6e6ed";

    expect(computeSignature(sharedSecret, timestamp, body)).toBe(expected);
  });

  it("accepts a valid signed POST request and calls revalidateTag for each tag", async () => {
    const now = 1000000;
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
    expect(mockRevalidateTag).toHaveBeenCalledWith("site");
    expect(mockRevalidateTag).toHaveBeenCalledWith("project:alpha");
  });

  it("supports legacy x-empire-* header names for backwards compatibility", async () => {
    const now = 1000000;
    const body = JSON.stringify({ tags: ["site"] });
    const signature = computeSignature(SECRET, now, body);

    const request = new Request("https://example.com/_internal/revalidate", {
      method: "POST",
      headers: {
        [LEGACY_SIGNATURE_HEADER]: signature,
        [LEGACY_TIMESTAMP_HEADER]: String(now),
        "content-type": "application/json",
      },
      body,
    });

    const result = await processRevalidate(request, { secret: SECRET, now });
    expect(result.ok).toBe(true);
    expect(result.status).toBe(200);
  });

  it("rejects suffixed or non-hex signatures (M3)", async () => {
    const now = 1000000;
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
    const now = 1000000;
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

    const first = await processRevalidate(makeReq(), { secret: SECRET, now });
    expect(first.ok).toBe(true);

    const replay = await processRevalidate(makeReq(), { secret: SECRET, now });
    expect(replay.ok).toBe(false);
    expect(replay.status).toBe(401);
  });

  it("rejects timestamps outside the 5-minute freshness window", async () => {
    const now = 1000000;
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

    const result = await processRevalidate(request, { secret: SECRET, now });
    expect(result.ok).toBe(false);
    expect(result.status).toBe(401);
  });

  it("rejects oversized request bodies exceeding 16 KB (N2)", async () => {
    const now = 1000000;
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
