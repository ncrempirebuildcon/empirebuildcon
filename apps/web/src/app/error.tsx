"use client";
/**
 * Friendly error state for any page segment (DESIGN_SYSTEM §8 "States": error + Try again).
 * Next.js 16 passes `retry()`, which re-fetches and re-renders the segment.
 * TODO(phase-5): report errors to Sentry (@sentry/nextjs) instead of the console.
 */
import { useEffect } from "react";
import Link from "next/link";
import { Button } from "@empire/ui";

export default function ErrorPage({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="grid min-h-dvh place-items-center px-4 py-12">
      <div role="alert" className="flex max-w-lg flex-col items-center gap-4 text-center">
        <h1 className="font-display text-h3 font-semibold">Something went wrong</h1>
        <p>We couldn&apos;t load this page. Please try again in a moment.</p>
        <div className="flex flex-wrap justify-center gap-3">
          <Button onClick={() => retry()}>Try again</Button>
          <Link href="/" className="inline-flex min-h-11 items-center px-2 font-bold">
            Home page
          </Link>
        </div>
      </div>
    </main>
  );
}
