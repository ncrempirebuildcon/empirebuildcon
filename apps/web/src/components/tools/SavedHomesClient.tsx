"use client";

/**
 * SavedHomesClient component (handbook/tasks/phase-5/5.7b-tools.md).
 *
 * Requirements:
 *   - Lists saved items from localStorage.
 *   - Verifies existence of each item through the public API via /api proxy:
 *       GET /api/v1/public/projects/{slug}
 *       GET /api/v1/public/projects/{slug}/configurations/{config}
 *   - 404 displays "No longer listed" with a Remove button, and NEVER displays stale prices.
 *   - Displays NO prices at all (only names and links).
 *   - Empty state links to /projects.
 *   - Privacy notice: "Saved only in this browser."
 */
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import {
  getSavedHomesSnapshot,
  getServerSavedHomesSnapshot,
  getSavedItems,
  removeSavedItem,
  subscribeSavedHomes,
  type SavedItem,
} from "@/lib/tools/saved";

interface ItemStatus {
  delisted: boolean;
  checked: boolean;
}

function noopSubscribe() {
  return () => {};
}

function getClientMounted() {
  return true;
}

function getServerMounted() {
  return false;
}

export function SavedHomesClient() {
  const isMounted = useSyncExternalStore(noopSubscribe, getClientMounted, getServerMounted);
  const snapshot = useSyncExternalStore(
    subscribeSavedHomes,
    getSavedHomesSnapshot,
    getServerSavedHomesSnapshot,
  );

  const items = useMemo(() => {
    if (!isMounted) return [];
    void snapshot;
    return getSavedItems();
  }, [isMounted, snapshot]);

  const [statusMap, setStatusMap] = useState<Record<string, ItemStatus>>({});
  const [announcement, setAnnouncement] = useState<string>("");

  useEffect(() => {
    if (!isMounted) return;

    async function checkItem(item: SavedItem) {
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

      if (!apiUrl) return;

      try {
        const res = await fetch(apiUrl, {
          method: "GET",
          cache: "no-store",
          headers: { Accept: "application/json" },
        });
        if (res.status === 404) {
          setStatusMap((prev) => ({
            ...prev,
            [item.path]: { delisted: true, checked: true },
          }));
        } else {
          setStatusMap((prev) => ({
            ...prev,
            [item.path]: { delisted: false, checked: true },
          }));
        }
      } catch {
        setStatusMap((prev) => ({
          ...prev,
          [item.path]: { delisted: false, checked: true },
        }));
      }
    }

    for (const item of items) {
      void checkItem(item);
    }
  }, [isMounted, items]);

  function handleRemove(path: string, name: string) {
    const res = removeSavedItem(path);
    if (res.success) {
      setAnnouncement(`${name} removed from saved homes`);
    }
  }

  if (!isMounted) {
    return (
      <div className="flex flex-col gap-4 py-8">
        <p className="text-body text-muted">Loading saved homes…</p>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 rounded-card border border-line bg-noir-800 p-12 text-center">
        <h2 className="font-display text-h3 font-semibold text-body">
          You haven&apos;t saved any homes yet
        </h2>
        <p className="max-w-md text-body text-muted">
          Browse our projects and properties and tap the Save button to keep track of homes you are
          interested in.
        </p>
        <Link
          href="/projects"
          className="inline-flex min-h-11 items-center justify-center rounded-pill border border-gold-500 bg-gold-500/10 px-6 font-semibold text-gold-300 transition-colors hover:bg-gold-500/20"
        >
          Explore projects
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <span aria-live="polite" className="sr-only">
        {announcement}
      </span>

      <ul className="flex flex-col gap-4" data-testid="saved-homes-list">
        {items.map((item) => {
          const status = statusMap[item.path];
          const isDelisted = status?.delisted ?? false;

          return (
            <li
              key={item.path}
              data-testid="saved-home-item"
              className="flex flex-col justify-between gap-4 rounded-card border border-gold-line bg-noir-800 p-5 sm:flex-row sm:items-center"
            >
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center gap-2">
                  <span className="text-caption font-semibold tracking-[0.08em] text-gold-400 uppercase">
                    {item.kind === "property" ? "Property" : "Project"}
                  </span>
                  {isDelisted ? (
                    <span
                      data-testid="delisted-badge"
                      className="rounded-chip border border-gold-line/40 bg-noir-900 px-2.5 py-0.5 text-caption font-semibold text-muted"
                    >
                      No longer listed
                    </span>
                  ) : null}
                </div>

                {isDelisted ? (
                  <span className="font-display text-h3 font-semibold text-muted">{item.name}</span>
                ) : (
                  <Link
                    href={item.path}
                    className="font-display text-h3 font-semibold text-body underline underline-offset-4 transition-colors hover:text-gold-300"
                  >
                    {item.name}
                  </Link>
                )}
              </div>

              <button
                type="button"
                onClick={() => handleRemove(item.path, item.name)}
                aria-label={`Remove ${item.name} from saved homes`}
                className="inline-flex min-h-11 items-center justify-center rounded-pill border border-line bg-noir-900 px-4 py-2 text-small font-semibold text-muted transition-colors hover:border-gold-line hover:text-body"
              >
                Remove
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
