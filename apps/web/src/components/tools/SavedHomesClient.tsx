"use client";

/**
 * SavedHomesClient component (handbook/tasks/phase-5/5.7b-tools.md).
 *
 * Requirements:
 *   - Lists saved items from localStorage.
 *   - Verifies existence of each item through the public API via /api proxy:
 *       GET /api/v1/public/projects/{slug}
 *       GET /api/v1/public/projects/{slug}/configurations/{config}
 *   - Checks at most 4 items concurrently, only re-checking items without status.
 *   - While an item is not yet verified, displays "Checking…" without a link.
 *   - 404 displays "No longer listed" with a Remove button, and NEVER displays stale prices.
 *   - COMPLIANCE (AGENTS.md "Honest content", D-002): Displays NO prices at all (only names and links).
 *   - Empty state links to /projects.
 *   - Privacy notice: "Saved only in this browser."
 *   - Accessible announcements and focus management on item removal.
 *
 * Collaborators: Antigravity <noreply@google.com>, Claude (review 1). Decisions: D-040, D-049.
 */
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { cx } from "@empire/ui";
import { useMounted } from "@/lib/tools/mounted";
import {
  getSavedHomesSnapshot,
  getServerSavedHomesSnapshot,
  getSavedItems,
  isStorageAvailable,
  removeSavedItem,
  subscribeSavedHomes,
} from "@/lib/tools/saved";

type CheckState = "pending" | "listed" | "delisted" | "failed";

interface ItemStatus {
  state: CheckState;
}

const MAX_CONCURRENT_CHECKS = 4;

export function SavedHomesClient() {
  const isMounted = useMounted();
  const snapshot = useSyncExternalStore(
    subscribeSavedHomes,
    getSavedHomesSnapshot,
    getServerSavedHomesSnapshot,
  );

  const [isStorageReady] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return isStorageAvailable();
  });

  const items = useMemo(() => {
    if (!isMounted || !isStorageReady) return [];
    void snapshot;
    return getSavedItems();
  }, [isMounted, isStorageReady, snapshot]);

  const [statusMap, setStatusMap] = useState<Record<string, ItemStatus>>({});
  const [announcement, setAnnouncement] = useState<string>("");

  const removeBtnRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const emptyHeadingRef = useRef<HTMLHeadingElement | null>(null);

  // Batched existence checking: checks at most 4 unchecked items at a time (Item 3 & 4)
  useEffect(() => {
    if (!isMounted || !isStorageReady || items.length === 0) return;

    const uncheckedItems = items.filter((item) => !statusMap[item.path]);
    if (uncheckedItems.length === 0) return;

    const batch = uncheckedItems.slice(0, MAX_CONCURRENT_CHECKS);
    let cancelled = false;

    async function checkBatch() {
      const results = await Promise.all(
        batch.map(async (item) => {
          const cleanPath = item.path.replace(/^\/projects\/?/, "");
          const parts = cleanPath.split("/").filter(Boolean);
          const projectSlug = parts[0];
          const configSlug = parts[1];

          let apiUrl = "";
          if (item.kind === "property" && projectSlug && configSlug) {
            apiUrl = `/api/v1/public/projects/${encodeURIComponent(projectSlug)}/configurations/${encodeURIComponent(configSlug)}`;
          } else if (projectSlug) {
            apiUrl = `/api/v1/public/projects/${encodeURIComponent(projectSlug)}`;
          }

          if (!apiUrl) {
            return { path: item.path, state: "delisted" as const };
          }

          try {
            const res = await fetch(apiUrl, {
              method: "GET",
              cache: "no-store",
              headers: { Accept: "application/json" },
            });
            if (res.status === 404) {
              return { path: item.path, state: "delisted" as const };
            }
            if (res.ok) {
              return { path: item.path, state: "listed" as const };
            }
            // 5xx or rate limit: stay a link, but not counted as verified delisted
            return { path: item.path, state: "failed" as const };
          } catch {
            return { path: item.path, state: "failed" as const };
          }
        }),
      );

      if (!cancelled) {
        setStatusMap((prev) => {
          const next = { ...prev };
          for (const r of results) {
            next[r.path] = { state: r.state };
          }
          return next;
        });
      }
    }

    void checkBatch();

    return () => {
      cancelled = true;
    };
  }, [isMounted, isStorageReady, items, statusMap]);

  function handleRemove(idx: number, path: string, name: string) {
    const res = removeSavedItem(path);
    if (res.success) {
      setAnnouncement(`${name} removed from saved homes`);

      const remainingLength = items.length - 1;
      if (remainingLength <= 0) {
        setTimeout(() => emptyHeadingRef.current?.focus(), 0);
      } else {
        const nextIdx = Math.min(idx, remainingLength - 1);
        setTimeout(() => removeBtnRefs.current[nextIdx]?.focus(), 0);
      }
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Polite live region rendered persistently across both empty and list branches (Must 5) */}
      <div aria-live="polite" className="sr-only">
        {announcement}
      </div>

      <noscript>
        <p className="rounded-card border border-gold-line bg-noir-800 p-4 text-small text-muted">
          Saved homes need JavaScript.
        </p>
      </noscript>

      {!isMounted ? (
        <div className="flex flex-col gap-4 py-8">
          <p className="text-body text-muted">Loading saved homes…</p>
        </div>
      ) : !isStorageReady ? (
        <div className="flex flex-col items-center justify-center gap-4 rounded-card border border-line bg-noir-800 p-12 text-center">
          <h2
            ref={emptyHeadingRef}
            tabIndex={-1}
            className="font-display text-h3 font-semibold text-body outline-none"
          >
            Saving isn&apos;t available in this browser
          </h2>
          <p className="max-w-md text-body text-muted">
            Please enable cookies or local storage in your browser settings to keep track of saved
            homes.
          </p>
          <Link
            href="/projects"
            className="inline-flex min-h-11 items-center justify-center rounded-pill border border-gold-500 bg-gold-500/10 px-6 font-semibold text-gold-300 transition-colors hover:bg-gold-500/20"
          >
            Explore projects
          </Link>
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 rounded-card border border-line bg-noir-800 p-12 text-center">
          <h2
            ref={emptyHeadingRef}
            tabIndex={-1}
            className="font-display text-h3 font-semibold text-body outline-none"
          >
            You haven&apos;t saved any homes yet
          </h2>
          <p className="max-w-md text-body text-muted">
            Browse our projects and properties and tap the Save button to keep track of homes you
            are interested in.
          </p>
          <Link
            href="/projects"
            className="inline-flex min-h-11 items-center justify-center rounded-pill border border-gold-500 bg-gold-500/10 px-6 font-semibold text-gold-300 transition-colors hover:bg-gold-500/20"
          >
            Explore projects
          </Link>
        </div>
      ) : (
        <ul className="flex flex-col gap-4" data-testid="saved-homes-list">
          {items.map((item, idx) => {
            const status = statusMap[item.path];
            const isDelisted = status?.state === "delisted";
            const isChecking = !status || status.state === "pending";

            return (
              <li
                key={item.path}
                data-testid="saved-home-item"
                className="flex flex-col justify-between gap-4 rounded-card border border-gold-line bg-noir-800 p-5 sm:flex-row sm:items-center"
              >
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center gap-2">
                    <span className="text-caption font-semibold uppercase tracking-[0.08em] text-gold-400">
                      {item.kind === "property" ? "Property" : "Project"}
                    </span>
                    {isDelisted ? (
                      <span
                        data-testid="delisted-badge"
                        className="rounded-pill border border-gold-line/40 bg-noir-900 px-2.5 py-0.5 text-caption font-semibold text-muted"
                      >
                        No longer listed
                      </span>
                    ) : isChecking ? (
                      <span className="rounded-pill border border-line bg-noir-900 px-2.5 py-0.5 text-caption font-medium text-muted">
                        Checking…
                      </span>
                    ) : null}
                  </div>

                  {/* COMPLIANCE (AGENTS.md "Honest content", D-002): strictly names and links only, no prices */}
                  {isDelisted ? (
                    <span className="font-display text-h3 font-semibold text-muted">
                      {item.name}
                    </span>
                  ) : isChecking ? (
                    <span className="font-display text-h3 font-semibold text-muted">
                      {item.name}
                    </span>
                  ) : (
                    <Link
                      href={item.path}
                      className={cx(
                        "inline-flex min-h-11 items-center font-display text-h3 font-semibold text-body underline underline-offset-4 transition-colors hover:text-gold-300",
                      )}
                    >
                      {item.name}
                    </Link>
                  )}
                </div>

                <button
                  ref={(el) => {
                    removeBtnRefs.current[idx] = el;
                  }}
                  type="button"
                  onClick={() => handleRemove(idx, item.path, item.name)}
                  aria-label={`Remove ${item.name} from saved homes`}
                  className="inline-flex min-h-11 items-center justify-center rounded-pill border border-line bg-noir-900 px-4 py-2 text-small font-semibold text-muted transition-colors hover:border-gold-line hover:text-body focus-visible:outline-2 focus-visible:outline-gold-400 focus-visible:outline-offset-2"
                >
                  Remove
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
