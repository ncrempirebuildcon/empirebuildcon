"use client";

/**
 * ShareLinks component (Phase 5 Task 5.5b).
 *
 * Implements:
 *   - Reusable share bar independent of post data (props: `url`, `title`).
 *   - Native share via `navigator.share` when supported; hidden otherwise.
 *   - Copy link: copies URL without query string or fragment; announces "Link copied" in polite live region.
 *   - WhatsApp share: link to `https://wa.me/?text=<encoded title and URL>`.
 *   - Zero third-party scripts or SDKs.
 *   - 44px minimum touch targets.
 */
import { useState, useSyncExternalStore } from "react";

export interface ShareLinksProps {
  url?: string;
  title: string;
  className?: string;
}

function subscribe() {
  return () => {};
}

function getCanShareSnapshot(): boolean {
  return typeof navigator !== "undefined" && typeof navigator.share === "function";
}

function getServerSnapshot(): boolean {
  return false;
}

/**
 * Strips query string and URL fragment from a URL.
 */
export function stripQueryAndFragment(rawUrl: string): string {
  if (!rawUrl) return "";
  try {
    const isRelative = rawUrl.startsWith("/");
    const base = isRelative ? "http://localhost" : undefined;
    const parsed = new URL(rawUrl, base);
    return isRelative ? parsed.pathname : `${parsed.origin}${parsed.pathname}`;
  } catch {
    const [beforeQuery = ""] = rawUrl.split("?");
    const [beforeHash = ""] = beforeQuery.split("#");
    return beforeHash;
  }
}

/**
 * Builds the WhatsApp share link with URL-encoded text.
 */
export function buildWhatsAppShareUrl(title: string, rawUrl: string): string {
  const cleanUrl = stripQueryAndFragment(rawUrl);
  const text = cleanUrl ? `${title} ${cleanUrl}`.trim() : title.trim();
  return `https://wa.me/?text=${encodeURIComponent(text)}`;
}

export function ShareLinks({ url, title, className = "" }: ShareLinksProps) {
  const canNativeShare = useSyncExternalStore(subscribe, getCanShareSnapshot, getServerSnapshot);
  const [copied, setCopied] = useState(false);

  const cleanUrl = stripQueryAndFragment(url || "");
  const whatsappHref = buildWhatsAppShareUrl(title, cleanUrl);

  const getFullShareUrl = (): string => {
    if (cleanUrl.startsWith("http")) return cleanUrl;
    if (typeof window !== "undefined") {
      return `${window.location.origin}${cleanUrl || window.location.pathname}`;
    }
    return cleanUrl;
  };

  const handleCopy = async () => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      try {
        await navigator.clipboard.writeText(getFullShareUrl());
        setCopied(true);
        setTimeout(() => setCopied(false), 3000);
      } catch {
        // Fallback if clipboard permission fails
      }
    }
  };

  const handleNativeShare = async () => {
    if (typeof navigator !== "undefined" && navigator.share) {
      try {
        await navigator.share({
          title,
          url: getFullShareUrl(),
        });
      } catch {
        // User cancelled or share aborted
      }
    }
  };

  return (
    <div className={`flex flex-wrap items-center gap-2.5 ${className}`}>
      {/* WhatsApp share link */}
      <a
        href={whatsappHref}
        target="_blank"
        rel="noopener noreferrer"
        aria-label="Share on WhatsApp"
        className="inline-flex min-h-[44px] items-center gap-2 rounded-full bg-palm-bg px-4 py-2.5 text-sm font-bold text-palm transition-colors hover:bg-palm-bg/80 focus-visible:outline-2 focus-visible:outline-gold-300"
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          aria-hidden="true"
        >
          <path d="M4 20l1.3-3.9A8 8 0 1 1 8 19.3L4 20z" />
        </svg>
        <span>WhatsApp</span>
      </a>

      {/* Native Web Share button (only rendered if supported) */}
      {canNativeShare && (
        <button
          type="button"
          onClick={handleNativeShare}
          aria-label="Share article"
          className="inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-full border border-gold-500 bg-transparent px-4 py-2.5 text-sm font-bold text-gold-300 transition-colors hover:bg-gold-500/10 focus-visible:outline-2 focus-visible:outline-gold-300"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            aria-hidden="true"
          >
            <circle cx="18" cy="5" r="3" />
            <circle cx="6" cy="12" r="3" />
            <circle cx="18" cy="19" r="3" />
            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
            <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
          </svg>
          <span>Share</span>
        </button>
      )}

      {/* Copy link button / Copied confirmation state */}
      {copied ? (
        <span
          role="status"
          aria-live="polite"
          className="inline-flex min-h-[44px] items-center gap-2 rounded-full border border-palm-line px-4 py-2.5 text-sm font-bold text-palm"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden="true"
          >
            <path d="M5 12l5 5 9-10" />
          </svg>
          <span>Link copied</span>
        </span>
      ) : (
        <button
          type="button"
          onClick={handleCopy}
          aria-label="Copy link"
          className="inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-full border border-gold-500 bg-transparent px-4 py-2.5 text-sm font-bold text-gold-300 transition-colors hover:bg-gold-500/10 focus-visible:outline-2 focus-visible:outline-gold-300"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            aria-hidden="true"
          >
            <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" />
          </svg>
          <span>Copy link</span>
        </button>
      )}
    </div>
  );
}

export default ShareLinks;
