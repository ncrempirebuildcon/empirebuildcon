import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  _clearReplayCache,
  computeSignature,
  processRevalidate,
  revalidateHandler,
  SIGNATURE_HEADER,
  TIMESTAMP_HEADER,
} from "../src/lib/public/revalidate";

vi.mock("next/cache", () => ({
  revalidateTag: vi.fn(),
}));

describe("POST /_internal/revalidate", () => {
  const secret = "test-secret-at-least-32-chars-long-here";
  let now = Date.now();

  beforeEach(() => {
    _clearReplayCache();
    process.env.REVALIDATE_SECRET = secret;
    now = Date.now();
  });

  function makeRequest(
    method: string,
    body: unknown,
    headers: Record<string, string> = {},
  ): Request {
    return new Request("http://localhost:3000/_internal/revalidate", {
      method,
      headers: {
        "Content-Type": "application/json",
        ...headers,
      },
      body: method !== "GET" ? JSON.stringify(body) : undefined,
    });
  }

  it("revalidates successfully with a valid signature and timestamp", async () => {
    const payload = { tags: ["site", "project:aurum"] };
    const bodyText = JSON.stringify(payload);
    const sig = computeSignature(secret, now, bodyText);

    const req = makeRequest("POST", payload, {
      [SIGNATURE_HEADER]: sig,
      [TIMESTAMP_HEADER]: String(now),
    });

    const res = await revalidateHandler(req);
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json).toEqual({ revalidated: true, tags: ["site", "project:aurum"] });
  });

  it("refuses wrong method with 405", async () => {
    const req = makeRequest("GET", null);
    const res = await revalidateHandler(req);
    expect(res.status).toBe(405);
  });

  it("refuses unsigned request with 401 and empty body", async () => {
    const req = makeRequest("POST", { tags: ["site"] });
    const res = await revalidateHandler(req);
    expect(res.status).toBe(401);
    const text = await res.text();
    expect(text).toBe("");
  });

  it("refuses invalid signature with 401", async () => {
    const req = makeRequest(
      "POST",
      { tags: ["site"] },
      {
        [SIGNATURE_HEADER]: "deadbeef".repeat(8),
        [TIMESTAMP_HEADER]: String(now),
      },
    );
    const res = await processRevalidate(req, { secret, now });
    expect(res.status).toBe(401);
  });

  it("refuses stale timestamp (> 5 minutes) with 401", async () => {
    const payload = { tags: ["site"] };
    const staleTime = now - 6 * 60 * 1000;
    const sig = computeSignature(secret, staleTime, JSON.stringify(payload));

    const req = makeRequest("POST", payload, {
      [SIGNATURE_HEADER]: sig,
      [TIMESTAMP_HEADER]: String(staleTime),
    });

    const res = await processRevalidate(req, { secret, now });
    expect(res.status).toBe(401);
  });

  it("refuses replayed requests with 401", async () => {
    const payload = { tags: ["site"] };
    const bodyText = JSON.stringify(payload);
    const sig = computeSignature(secret, now, bodyText);

    const req1 = makeRequest("POST", payload, {
      [SIGNATURE_HEADER]: sig,
      [TIMESTAMP_HEADER]: String(now),
    });
    const res1 = await processRevalidate(req1, { secret, now });
    expect(res1.status).toBe(200);

    // Same signature sent a second time -> replay refused
    const req2 = makeRequest("POST", payload, {
      [SIGNATURE_HEADER]: sig,
      [TIMESTAMP_HEADER]: String(now),
    });
    const res2 = await processRevalidate(req2, { secret, now });
    expect(res2.status).toBe(401);
  });

  it("refuses missing or empty tags with 401", async () => {
    const payload = { tags: [] };
    const bodyText = JSON.stringify(payload);
    const sig = computeSignature(secret, now, bodyText);

    const req = makeRequest("POST", payload, {
      [SIGNATURE_HEADER]: sig,
      [TIMESTAMP_HEADER]: String(now),
    });

    const res = await processRevalidate(req, { secret, now });
    expect(res.status).toBe(401);
  });
});
