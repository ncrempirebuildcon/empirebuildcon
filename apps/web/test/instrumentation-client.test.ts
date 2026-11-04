import { afterEach, describe, expect, it, vi } from "vitest";

// The real config would start Sentry; here we only need to know whether it was loaded.
const loaded = vi.fn();

type Listener = () => void;

function fakeBrowser(readyState: "loading" | "complete") {
  const listeners: Record<string, Listener[]> = {};
  vi.stubGlobal("document", { readyState });
  vi.stubGlobal("window", {
    addEventListener: (name: string, fn: Listener) => {
      (listeners[name] ??= []).push(fn);
    },
  });
  return { fire: (name: string) => listeners[name]?.forEach((fn) => fn()) };
}

async function startClient(): Promise<void> {
  vi.resetModules();
  vi.doMock("../sentry.client.config", () => {
    loaded();
    return {};
  });
  await import("../src/instrumentation-client");
  // Let the dynamic import inside settle.
  await new Promise((resolve) => setTimeout(resolve, 0));
}

afterEach(() => {
  loaded.mockClear();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("instrumentation-client (task 5.7, D-049)", () => {
  it("never loads the Sentry SDK without a DSN", async () => {
    vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "");
    const browser = fakeBrowser("complete");
    await startClient();
    browser.fire("load");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(loaded).not.toHaveBeenCalled();
  });

  it("with a DSN, waits for the page to load before loading the SDK", async () => {
    vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "https://key@o1.ingest.sentry.io/1");
    const browser = fakeBrowser("loading");
    await startClient();
    expect(loaded).not.toHaveBeenCalled();
    browser.fire("load");
    await vi.waitFor(() => expect(loaded).toHaveBeenCalledTimes(1));
  });

  it("with a DSN on an already loaded page, loads the SDK at once", async () => {
    vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "https://key@o1.ingest.sentry.io/1");
    fakeBrowser("complete");
    await startClient();
    await vi.waitFor(() => expect(loaded).toHaveBeenCalledTimes(1));
  });
});
