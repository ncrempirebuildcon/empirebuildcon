"use client";

/**
 * SaveButton client component for project and property pages (handbook/tasks/phase-5/5.7b-tools.md).
 *
 * Requirements:
 *   - Real <button> with aria-pressed.
 *   - Label toggles between "Save" and "Saved".
 *   - Subscribes to storage events so state remains synchronized across tabs.
 *   - Change is announced politely via aria-live="polite".
 *   - Reads and writes to localStorage wrapped in safe checks.
 *   - If storage is blocked or unavailable, displays "Saving isn't available in this browser".
 *   - Browser only, no network calls or tracking.
 *
 * Collaborators: Antigravity <noreply@google.com>, Claude (reviews 1 & 2). Decisions: D-040, D-049.
 */
import { useMemo, useState, useSyncExternalStore } from "react";
import { cx } from "@empire/ui";
import { useMounted } from "@/lib/tools/mounted";
import {
  addSavedItem,
  getSavedHomesSnapshot,
  getServerSavedHomesSnapshot,
  isItemSaved,
  isStorageAvailable,
  removeSavedItem,
  subscribeSavedHomes,
  type SavedItemKind,
} from "@/lib/tools/saved";

export interface SaveButtonProps {
  kind: SavedItemKind;
  path: string;
  name: string;
  className?: string;
}

export function SaveButton({ kind, path, name, className }: SaveButtonProps) {
  const isMounted = useMounted();

  // Storage check executed once on client mount (Item 6: avoid test-key writes on every render)
  const [isStorageReady] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return isStorageAvailable();
  });

  // Subscribe to storage changes across components and browser tabs (Item 6)
  const snapshot = useSyncExternalStore(
    subscribeSavedHomes,
    getSavedHomesSnapshot,
    getServerSavedHomesSnapshot,
  );

  const [announcement, setAnnouncement] = useState<string>("");

  // Determine isSaved directly from snapshot/storage without stale local overrides (Item 6)
  const isSaved = useMemo(() => {
    if (!isMounted || !isStorageReady) return false;
    void snapshot; // Track snapshot change
    return isItemSaved(path);
  }, [isMounted, isStorageReady, snapshot, path]);

  const handleToggle = () => {
    if (!isStorageReady) return;

    if (isSaved) {
      const res = removeSavedItem(path);
      if (res.success) {
        setAnnouncement(`${name} removed from saved homes`);
      } else {
        setAnnouncement("Couldn't update saved homes in this browser");
      }
    } else {
      const res = addSavedItem({ kind, path, name });
      if (res.success) {
        setAnnouncement(`${name} saved to this browser`);
      } else {
        setAnnouncement("Couldn't save in this browser");
      }
    }
  };

  if (!isMounted) {
    // SSR / initial hydration skeleton
    return (
      <div className="inline-flex flex-col gap-1">
        <button
          type="button"
          disabled
          aria-label={`Save ${name}`}
          className={cx(
            "inline-flex min-h-11 items-center justify-center gap-2 rounded-pill border border-gold-line bg-noir-800 px-4 py-2 text-small font-semibold text-muted opacity-80",
            className,
          )}
        >
          <SaveIcon filled={false} />
          <span>Save</span>
        </button>
        <noscript>
          <span className="text-caption text-muted">Saved homes need JavaScript</span>
        </noscript>
      </div>
    );
  }

  if (!isStorageReady) {
    return (
      <button
        type="button"
        disabled
        aria-disabled="true"
        title="Saving isn't available in this browser"
        aria-label="Saving isn't available in this browser"
        className={cx(
          "inline-flex min-h-11 items-center justify-center gap-2 rounded-pill border border-line bg-noir-800/60 px-4 py-2 text-small font-semibold text-muted opacity-70 cursor-not-allowed",
          className,
        )}
      >
        <SaveIcon filled={false} />
        <span>Saving isn&apos;t available in this browser</span>
      </button>
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={handleToggle}
        aria-pressed={isSaved}
        aria-label={isSaved ? `Saved ${name}. Press to remove from saved homes` : `Save ${name}`}
        className={cx(
          "inline-flex min-h-11 items-center justify-center gap-2 rounded-pill border px-4 py-2 text-small font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-gold-400 focus-visible:outline-offset-2",
          isSaved
            ? "border-gold-500 bg-gold-500/15 text-gold-300 hover:border-gold-400 hover:bg-gold-500/25"
            : "border-gold-line bg-noir-800 text-body hover:border-gold-500/60 hover:text-gold-300",
          className,
        )}
      >
        <SaveIcon filled={isSaved} />
        <span>{isSaved ? "Saved" : "Save"}</span>
      </button>
      <span aria-live="polite" className="sr-only">
        {announcement}
      </span>
    </>
  );
}

function SaveIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="shrink-0"
    >
      <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
    </svg>
  );
}
