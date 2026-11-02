"use client";
/**
 * Active offer banner: plain dismissible strip with the offer's terms line (D-035, S8).
 *
 * Implements:
 *   - Placement = banner from GET /api/v1/public/site.
 *   - No countdown timer or artificial urgency.
 *   - Valid date range displayed per DESIGN_SYSTEM ("Valid [start] – [end]").
 *   - 44px min touch targets for CTA and dismiss button (S8).
 *   - Dismissible via close button; persists dismissal during browser session via sessionStorage (S8).
 */
import { useState, useSyncExternalStore } from "react";
import Link from "next/link";
import type { PublicSite } from "@/lib/public/api";

type OfferItem = PublicSite["offers"][number];

function formatDate(iso?: string | null): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  } catch {
    return iso;
  }
}

export function OfferBanner({ offers }: { offers?: OfferItem[] }) {
  const [userDismissed, setUserDismissed] = useState(false);

  const bannerOffer = offers?.find((o) => o.placement === "banner");
  const offerKey = bannerOffer ? `dismissed_offer_${bannerOffer.id}` : "";

  const isStoredDismissed = useSyncExternalStore(
    (onStoreChange) => {
      window.addEventListener("storage", onStoreChange);
      return () => window.removeEventListener("storage", onStoreChange);
    },
    () => {
      if (!offerKey || typeof window === "undefined") return false;
      try {
        return sessionStorage.getItem(offerKey) === "1";
      } catch {
        return false;
      }
    },
    () => false,
  );

  const dismissed = userDismissed || isStoredDismissed;

  if (!bannerOffer || dismissed) {
    return null;
  }

  function handleDismiss() {
    setUserDismissed(true);
    if (offerKey && typeof window !== "undefined") {
      try {
        sessionStorage.setItem(offerKey, "1");
      } catch {
        // Ignore sessionStorage errors
      }
    }
  }

  const startDate = formatDate(bannerOffer.starts_at);
  const endDate = formatDate(bannerOffer.ends_at);
  const validityText =
    startDate && endDate
      ? `Valid ${startDate} – ${endDate}`
      : endDate
        ? `Valid until ${endDate}`
        : startDate
          ? `Valid from ${startDate}`
          : "";

  return (
    <aside
      aria-label="Promotional announcement"
      className="relative border-b border-gold-500/40 bg-noir-800 px-4 py-3 text-sand-200"
      data-testid="offer-banner"
    >
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 pr-12">
        <div className="flex flex-col gap-0.5 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-display text-xs font-semibold tracking-wider text-gold-400">
              OFFER
            </span>
            <strong className="text-sand-100">{bannerOffer.title}</strong>
            {validityText && (
              <span className="text-xs text-sand-400 font-medium">({validityText})</span>
            )}
          </div>
          {bannerOffer.body && <p className="text-xs text-sand-300">{bannerOffer.body}</p>}
          {bannerOffer.terms && (
            <span className="text-[11px] text-sand-400">
              {bannerOffer.terms}
              {bannerOffer.terms_url && (
                <>
                  {" · "}
                  <Link href={bannerOffer.terms_url} className="underline hover:text-gold-300">
                    Terms apply
                  </Link>
                </>
              )}
            </span>
          )}
        </div>

        {bannerOffer.cta_url && bannerOffer.cta_label && (
          <Link
            href={bannerOffer.cta_url}
            className="inline-flex min-h-[44px] items-center rounded-full bg-gold-500 px-5 text-xs font-extrabold text-noir-900 shadow-md hover:bg-gold-400"
          >
            {bannerOffer.cta_label}
          </Link>
        )}
      </div>

      <button
        type="button"
        aria-label="Dismiss offer"
        onClick={handleDismiss}
        className="absolute top-2 right-2 flex h-11 w-11 min-h-[44px] min-w-[44px] items-center justify-center rounded-full text-sand-400 hover:bg-noir-700 hover:text-sand-100"
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
          <path d="M18 6L6 18M6 6l12 12" />
        </svg>
      </button>
    </aside>
  );
}

export default OfferBanner;
