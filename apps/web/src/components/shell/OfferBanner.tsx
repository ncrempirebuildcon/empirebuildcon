"use client";
/**
 * Active offer banner: plain dismissible strip with the offer's terms line (D-035).
 *
 * Implements:
 *   - Placement = banner from GET /api/v1/public/site.
 *   - No countdown timer or artificial urgency.
 *   - Dismissible via close button; persists dismissal during session.
 */
import { useState } from "react";
import Link from "next/link";
import type { PublicSite } from "@/lib/public/api";

type OfferItem = PublicSite["offers"][number];

export function OfferBanner({ offers }: { offers?: OfferItem[] }) {
  const [dismissed, setDismissed] = useState(false);

  const bannerOffer = offers?.find((o) => o.placement === "banner");
  if (!bannerOffer || dismissed) {
    return null;
  }

  return (
    <aside
      aria-label="Promotional announcement"
      className="relative border-b border-gold-500/40 bg-noir-800 px-4 py-3 text-sand-200"
      data-testid="offer-banner"
    >
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 pr-8">
        <div className="flex flex-col gap-0.5 text-sm">
          <div className="flex items-center gap-2">
            <span className="font-display text-xs font-semibold tracking-wider text-gold-400">
              OFFER
            </span>
            <strong className="text-sand-100">{bannerOffer.title}</strong>
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
            className="inline-flex min-h-[36px] items-center rounded-full bg-gold-500 px-4 text-xs font-extrabold text-noir-900 hover:bg-gold-400"
          >
            {bannerOffer.cta_label}
          </Link>
        )}
      </div>

      <button
        type="button"
        aria-label="Dismiss offer"
        onClick={() => setDismissed(true)}
        className="absolute top-3 right-3 flex h-8 w-8 items-center justify-center rounded-full text-sand-400 hover:bg-noir-700 hover:text-sand-100"
      >
        <svg
          width="16"
          height="16"
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
