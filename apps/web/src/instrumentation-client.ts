/**
 * Next.js client instrumentation hook (Phase 5 task 5.2, M4; task 5.7, D-049).
 *
 * Starts Sentry in the browser only when NEXT_PUBLIC_SENTRY_DSN is set, and only after the page
 * has loaded.
 *
 * PERF (task 5.7): the Sentry browser SDK is ~118 KB gzipped. A static import put it in the
 * first bundle of every page even with no DSN (Lighthouse "unused JavaScript", slower LCP on
 * phones). As a separate chunk loaded after `load`, it never delays the first paint. Errors in
 * the very first moments of a page are the trade-off; the server side still reports them.
 */
const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn && typeof window !== "undefined") {
  const start = () => void import("../sentry.client.config");
  if (document.readyState === "complete") start();
  else window.addEventListener("load", start, { once: true });
}

export {};
