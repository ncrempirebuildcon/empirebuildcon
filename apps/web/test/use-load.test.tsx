// @vitest-environment jsdom
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useLoad } from "../src/components/admin/useLoad";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe("useLoad (task 5.8)", () => {
  it("drops a refresh that ends after the key changed", async () => {
    const slow = deferred<string[]>();
    let call = 0;
    const { result, rerender } = renderHook(
      ({ filter }: { filter: string }) =>
        useLoad(`offers:${filter}`, () => {
          call += 1;
          if (filter === "") return call === 1 ? Promise.resolve(["all-1"]) : slow.promise;
          return Promise.resolve(["live-only"]);
        }),
      { initialProps: { filter: "" } },
    );
    await waitFor(() => expect(result.current.data).toEqual(["all-1"]));

    // A save refreshes the unfiltered list; while that is slow, the visitor picks "Live".
    let refreshing!: Promise<unknown>;
    act(() => {
      refreshing = result.current.refresh();
    });
    rerender({ filter: "live" });
    await waitFor(() => expect(result.current.data).toEqual(["live-only"]));

    // The old refresh lands now; the "Live" list must stay.
    await act(async () => {
      slow.resolve(["all-2"]);
      await refreshing;
    });
    expect(result.current.data).toEqual(["live-only"]);
    expect(result.current.loading).toBe(false);
  });

  it("applies a refresh when the key hasn't changed", async () => {
    let n = 0;
    const { result } = renderHook(() => useLoad("k", () => Promise.resolve(++n)));
    await waitFor(() => expect(result.current.data).toBe(1));
    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.data).toBe(2);
  });
});
