"use client";

/**
 * ShareLinks component (Phase 5 Task 5.5b).
 *
 * Implements:
 *   - Reusable share bar independent of post data (props: `url`, `title`).
 *   - Native share via `navigator.share` when supported; hidden otherwise.
 *   - Copy link: copies clean URL without query string or fragment.
 *   - WhatsApp share: link to `https://wa.me/?text=<encoded title and absolute URL>`.
 *   - Button remains mounted on copy so focus never drops to body.
 *   - Persistent polite live region in the DOM for accessible status announcement.
 *   - Zero third-party scripts or SDKs.
 *   - 44px minimum touch targets.
 */
import { useState, useSyncExternalStore } from "react";

export interface ShareLinksProps {
  url?: string;
  title: string;
  className?: string;
}

function noopSubscribe() {
  return () => {};
}

/**
 * Determines whether native Web Share is supported by the environment.
 */
export function canShare(nav?: { share?: unknown } | null): boolean {
  return Boolean(nav && typeof nav.share === "function");
}

function getCanShareSnapshot(): boolean {
  return typeof navigator !== "undefined" && canShare(navigator);
}

function getServerCanShareSnapshot(): boolean {
  return false;
}

function getOriginSnapshot(): string {
  return typeof window !== "undefined" ? window.location.origin : "";
}

function getServerOriginSnapshot(): string {
  return "";
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
 * Resolves a raw URL (relative or absolute) to an absolute URL using the provided origin.
 * Strips query parameters and fragments.
 */
export function resolveShareUrl(rawUrl: string | undefined, origin?: string): string {
  if (!rawUrl && !origin) return "";
  const clean = stripQueryAndFragment(rawUrl || "");
  if (clean.startsWith("http://") || clean.startsWith("https://")) {
    return clean;
  }
  if (origin) {
    const base = origin.replace(/\/+$/, "");
    const path = clean.startsWith("/") ? clean : `/${clean}`;
    return `${base}${path}`;
  }
  return clean;
}

/**
 * Builds the WhatsApp share link with URL-encoded text and absolute URL.
 */
export function buildWhatsAppShareUrl(title: string, rawUrl: string, origin?: string): string {
  const fullUrl = resolveShareUrl(rawUrl, origin);
  const isAbsolute = fullUrl.startsWith("http://") || fullUrl.startsWith("https://");
  const text = isAbsolute ? `${title} ${fullUrl}`.trim() : title.trim();
  return `https://wa.me/?text=${encodeURIComponent(text)}`;
}

export function ShareLinks({ url, title, className = "" }: ShareLinksProps) {
  const isNativeShareSupported = useSyncExternalStore(
    noopSubscribe,
    getCanShareSnapshot,
    getServerCanShareSnapshot,
  );
  const clientOrigin = useSyncExternalStore(
    noopSubscribe,
    getOriginSnapshot,
    getServerOriginSnapshot,
  );
  const [copied, setCopied] = useState(false);

  const whatsappHref = buildWhatsAppShareUrl(title, url || "", clientOrigin);

  const getFullShareUrl = (): string => {
    return resolveShareUrl(
      url || (typeof window !== "undefined" ? window.location.pathname : ""),
      clientOrigin || (typeof window !== "undefined" ? window.location.origin : ""),
    );
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
      {isNativeShareSupported && (
        <button
          type="button"
          onClick={handleNativeShare}
          aria-label="Share this page"
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

      {/* Copy link button - always remains mounted in DOM to preserve focus */}
      <button
        type="button"
        onClick={handleCopy}
        aria-label={copied ? "Link copied" : "Copy link"}
        className={`inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-full border px-4 py-2.5 text-sm font-bold transition-colors focus-visible:outline-2 focus-visible:outline-gold-300 ${
          copied
            ? "border-palm-line bg-palm-bg/30 text-palm"
            : "border-gold-500 bg-transparent text-gold-300 hover:bg-gold-500/10"
        }`}
      >
        {copied ? (
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
        ) : (
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
        )}
        <span>{copied ? "Link copied" : "Copy link"}</span>
      </button>

      {/* Persistent polite live region for screen readers */}
      <span role="status" aria-live="polite" className="sr-only">
        {copied ? "Link copied" : ""}
      </span>
    </div>
  );
}

export default ShareLinks;
