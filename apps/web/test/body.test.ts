/** readCapped (L2 security review): stops reading past the limit, even without Content-Length. */
import { describe, expect, it } from "vitest";
import { readCapped } from "../src/lib/body";

function chunked(parts: string[]): Request {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const part of parts) controller.enqueue(new TextEncoder().encode(part));
      controller.close();
    },
  });
  return new Request("https://x/_internal/csp-report", {
    method: "POST",
    body: stream,
    duplex: "half",
  } as RequestInit);
}

describe("readCapped", () => {
  it("returns the text when it fits", async () => {
    expect(await readCapped(chunked(['{"a":', "1}"]), 16)).toBe('{"a":1}');
  });

  it("returns null past the limit, without a Content-Length", async () => {
    const req = chunked(["x".repeat(10), "x".repeat(10)]);
    expect(req.headers.get("content-length")).toBeNull();
    expect(await readCapped(req, 16)).toBeNull();
  });

  it("an empty body is empty text", async () => {
    expect(await readCapped(new Request("https://x/", { method: "POST" }), 16)).toBe("");
  });
});
