"use client";
/**
 * Loads data for a CMS screen and tracks loading, error and retry.
 *
 * How it works:
 *   1. `key` names what is wanted (e.g. the list filters). When it changes, the loader runs again;
 *      an answer that arrives for an older key is dropped, so a slow request can never overwrite
 *      a newer one.
 *   2. `loading` is derived (the last answer is for another key), so no state is set during the
 *      effect itself (React's "set-state-in-effect" rule).
 *   3. `reload()` retries with the same key (the "Try again" button). `replace()` swaps in data the
 *      screen already has, e.g. the saved project returned by a PATCH, without a new request.
 *   4. `refresh()` fetches again quietly: `loading` stays false, so the screen is not replaced by
 *      a skeleton and unsaved form fields stay as they are.
 */
import { useEffect, useEffectEvent, useState } from "react";

interface Result<T> {
  key: string;
  data?: T;
  error?: unknown;
}

export function useLoad<T>(key: string, loader: () => Promise<T>) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result<T> | null>(null);
  const fullKey = `${key}#${attempt}`;
  const runLoader = useEffectEvent(loader);

  useEffect(() => {
    let current = true;
    runLoader().then(
      (data) => {
        if (current) setResult({ key: fullKey, data });
      },
      (error: unknown) => {
        if (current) setResult({ key: fullKey, error });
      },
    );
    return () => {
      current = false;
    };
  }, [fullKey]);

  const isCurrent = result?.key === fullKey;
  return {
    /** The latest data; while a new key loads this is still the previous data. */
    data: result?.data,
    error: isCurrent ? result?.error : undefined,
    loading: !isCurrent,
    reload: () => setAttempt((n) => n + 1),
    replace: (data: T) => setResult({ key: fullKey, data }),
    refresh: async () => {
      const data = await loader();
      setResult({ key: fullKey, data });
      return data;
    },
  };
}
