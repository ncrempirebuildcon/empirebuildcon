"use client";
/**
 * Segment error state (DESIGN_SYSTEM §8 "States": error + Try again).
 *
 * Implements:
 *   - Captures error via Sentry (@sentry/nextjs), which scrubs URLs and personal data.
 *   - Next.js 16 `retry()` re-fetches and re-renders the segment.
 *
 * PERF (task 5.7c, D-049): Next.js loads the root error boundary with every page, so a static
 * Sentry import put the SDK core (~15 KB gzipped) in every page's first bundle, even with no DSN.
 * It is imported only when an error is actually shown.
 */
import { useEffect } from "react";
import Link from "next/link";
import { Button } from "@empire/ui";

export default function ErrorPage({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    // WHY the catch: if the chunk can't load (offline, or an old chunk after a deploy), the
    // visitor still sees this page; the server side reports its own errors.
    void import("@sentry/nextjs").then((Sentry) => Sentry.captureException(error)).catch(() => {});
  }, [error]);

  return (
    <main className="grid min-h-[70vh] place-items-center px-4 py-16">
      <div role="alert" className="flex max-w-lg flex-col items-center gap-4 text-center">
        <h1 className="font-display text-2xl md:text-3xl font-semibold text-sand-100">
          Something went wrong
        </h1>
        <p className="text-sand-300 text-sm md:text-base">
          We couldn&apos;t load this page. Please try again in a moment.
        </p>
        <div className="flex flex-wrap justify-center gap-3 pt-2">
          <Button onClick={() => retry()}>Try again</Button>
          <Link
            href="/"
            className="inline-flex min-h-[44px] items-center rounded-full border border-gold-500 px-5 text-sm font-bold text-gold-300 hover:bg-gold-500/10"
          >
            Home page
          </Link>
        </div>
      </div>
    </main>
  );
}
