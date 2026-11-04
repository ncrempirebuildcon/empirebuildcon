"use client";

/**
 * SaveButton client component for project and property pages (handbook/tasks/phase-5/5.7b-tools.md).
 *
 * Requirements:
 *   - Real <button> with aria-pressed.
 *   - Label toggles between "Save" and "Saved".
 *   - Change is announced politely via aria-live="polite".
 *   - Reads and writes to localStorage wrapped in try/catch.
 *   - If storage is blocked or unavailable, displays "Saving isn't available in this browser".
 *   - Browser only, no network calls or tracking.
 */
import { useState, useSyncExternalStore } from "react";
import {
  addSavedItem,
  isItemSaved,
  isStorageAvailable,
  removeSavedItem,
  type SavedItemKind,
} from "@/lib/tools/saved";

export interface SaveButtonProps {
  kind: SavedItemKind;
  path: string;
  name: string;
  className?: string;
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

export function SaveButton({ kind, path, name, className = "" }: SaveButtonProps) {
  const isMounted = useSyncExternalStore(noopSubscribe, getClientMounted, getServerMounted);
  const [toggleOverride, setToggleOverride] = useState<boolean | null>(null);
  const [storageBlockedOverride, setStorageBlockedOverride] = useState(false);
  const [announcement, setAnnouncement] = useState<string>("");

  const storageAvailable = isMounted && isStorageAvailable() && !storageBlockedOverride;
  const isSaved =
    toggleOverride !== null
      ? toggleOverride
      : isMounted && storageAvailable
        ? isItemSaved(path)
        : false;

  const handleToggle = () => {
    if (!storageAvailable) return;

    if (isSaved) {
      const res = removeSavedItem(path);
      if (res.success) {
        setToggleOverride(false);
        setAnnouncement(`${name} removed from saved homes`);
      } else {
        setStorageBlockedOverride(true);
      }
    } else {
      const res = addSavedItem({ kind, path, name });
      if (res.success) {
        setToggleOverride(true);
        setAnnouncement(`${name} saved to this browser`);
      } else {
        setStorageBlockedOverride(true);
      }
    }
  };

  if (!isMounted) {
    // SSR / initial hydration skeleton
    return (
      <button
        type="button"
        disabled
        aria-label={`Save ${name}`}
        className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-pill border border-gold-line bg-noir-800 px-4 py-2 text-small font-semibold text-muted opacity-80 ${className}`}
      >
        <SaveIcon filled={false} />
        <span>Save</span>
      </button>
    );
  }

  if (!storageAvailable) {
    return (
      <button
        type="button"
        disabled
        title="Saving isn't available in this browser"
        aria-label="Saving isn't available in this browser"
        className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-pill border border-line bg-noir-800/60 px-4 py-2 text-small font-semibold text-muted opacity-70 cursor-not-allowed ${className}`}
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
        className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-pill border px-4 py-2 text-small font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-gold-400 focus-visible:outline-offset-2 ${
          isSaved
            ? "border-gold-500 bg-gold-500/15 text-gold-300 hover:border-gold-400 hover:bg-gold-500/25"
            : "border-gold-line bg-noir-800 text-body hover:border-gold-500/60 hover:text-gold-200"
        } ${className}`}
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
