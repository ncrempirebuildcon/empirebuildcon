"use client";
/**
 * Consent banner component (Phase 6 Task 6.1, Scope 2).
 *
 * Implements DPDP Act (2023) consent requirements, D-056:
 * - Only mounts and displays when `enabled` is true AND consent is not yet chosen (or re-opened via settings).
 * - Renders nothing on server and nothing before hydration (no layout shift).
 * - Fixed to bottom (mobile: sits above MobileActionBar; desktop: bottom-left card).
 * - Equal prominence for Accept all and Reject all (same variant, side-by-side, identical classes).
 * - Accessible: landmark region, heading, visible focus, focus restored to opener, touch targets >= 44x44 px.
 * - All wording in CONSENT_COPY starts with [DRAFT] until legal review.
 */
import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Button, Switch } from "@empire/ui";
import { OPEN_SETTINGS_EVENT_NAME, readConsent, subscribe, writeConsent } from "@/lib/consent";

export const CONSENT_COPY = {
  heading: "[DRAFT] Cookies on this site",
  description:
    "[DRAFT] We use necessary cookies to run this site. With your permission we'd also use analytics cookies to see how the site is used, and marketing cookies to measure our ads. Nothing is turned on until you choose.",
  privacyLink: "[DRAFT] Privacy policy",
  acceptAll: "[DRAFT] Accept all",
  rejectAll: "[DRAFT] Reject all",
  choose: "[DRAFT] Choose",
  save: "[DRAFT] Save choices",
  necessaryTitle: "[DRAFT] Necessary",
  necessaryText: "[DRAFT] Needed for the site to work, always on.",
  analyticsTitle: "[DRAFT] Analytics",
  analyticsText: "[DRAFT] Count visits and pages, without your name.",
  marketingTitle: "[DRAFT] Marketing",
  marketingText: "[DRAFT] Measure which ads bring visitors.",
  // 6.1 review, Nit 1: the switches' state words belong with the rest of the wording.
  alwaysOn: "[DRAFT] Always on",
  on: "[DRAFT] On",
  off: "[DRAFT] Off",
} as const;

export interface ConsentBannerProps {
  /** True when tracking IDs (gtm_id, ga4_id, or meta_pixel_id) are configured. */
  enabled: boolean;
}

type BannerView = "prompt" | "choose";

const emptySubscribe = () => () => {};

export function ConsentBanner({ enabled }: ConsentBannerProps) {
  // Post-hydration guard to prevent layout shift and server mismatch
  const mounted = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

  // Sync with stored consent
  const consent = useSyncExternalStore(subscribe, readConsent, () => null);

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [view, setView] = useState<BannerView>("prompt");
  const [analytics, setAnalytics] = useState(false);
  const [marketing, setMarketing] = useState(false);

  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const openerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    // Listen for re-open requests from "Cookie settings" button
    const handleOpenSettings = () => {
      openerRef.current = (document.activeElement as HTMLElement) || null;
      const current = readConsent();
      setAnalytics(current ? current.analytics : false);
      setMarketing(current ? current.marketing : false);
      setView("choose");
      setSettingsOpen(true);
    };

    window.addEventListener(OPEN_SETTINGS_EVENT_NAME, handleOpenSettings);

    return () => {
      window.removeEventListener(OPEN_SETTINGS_EVENT_NAME, handleOpenSettings);
    };
  }, []);

  // When re-opened via settings, move focus to the heading once mounted
  useEffect(() => {
    if (settingsOpen && openerRef.current && headingRef.current) {
      headingRef.current.focus();
    }
  }, [settingsOpen]);

  const isOpen = mounted && enabled && (consent === null || settingsOpen);

  if (!isOpen) {
    return null;
  }

  const closeAndRestoreFocus = () => {
    setSettingsOpen(false);
    if (openerRef.current && typeof openerRef.current.focus === "function") {
      openerRef.current.focus();
    }
    openerRef.current = null;
  };

  const handleAcceptAll = () => {
    writeConsent({ analytics: true, marketing: true });
    closeAndRestoreFocus();
  };

  const handleRejectAll = () => {
    writeConsent({ analytics: false, marketing: false });
    closeAndRestoreFocus();
  };

  const handleSaveChoices = () => {
    writeConsent({ analytics, marketing });
    closeAndRestoreFocus();
  };

  // Shared button class for Accept all and Reject all to guarantee equal visual weight and size
  const actionButtonClasses = "flex-1 min-h-11";

  return (
    <section
      role="region"
      aria-label="Cookie choices"
      className="fixed z-50 bottom-[calc(64px+env(safe-area-inset-bottom))] md:bottom-6 left-3 right-3 md:left-6 md:right-auto md:max-w-md rounded-2xl md:rounded-xl border border-gold-500/40 bg-noir-800/98 p-5 shadow-2xl backdrop-blur-md text-sand-300"
    >
      <div className="flex flex-col gap-4">
        <div>
          <h2
            ref={headingRef}
            tabIndex={-1}
            className="font-display text-base font-bold text-sand-100 outline-none"
          >
            {CONSENT_COPY.heading}
          </h2>
          {view === "prompt" ? (
            <p className="mt-2 text-xs leading-relaxed text-sand-400">
              {CONSENT_COPY.description}{" "}
              <Link
                href="/privacy"
                className="text-gold-400 underline hover:text-gold-300 focus-visible:outline-2 focus-visible:outline-gold-400"
              >
                {CONSENT_COPY.privacyLink}
              </Link>
            </p>
          ) : null}
        </div>

        {view === "prompt" ? (
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-3">
              <Button variant="secondary" onClick={handleAcceptAll} className={actionButtonClasses}>
                {CONSENT_COPY.acceptAll}
              </Button>
              <Button variant="secondary" onClick={handleRejectAll} className={actionButtonClasses}>
                {CONSENT_COPY.rejectAll}
              </Button>
            </div>
            <div className="flex justify-center">
              <Button
                variant="tertiary"
                onClick={() => setView("choose")}
                className="min-h-11 min-w-11 text-xs"
              >
                {CONSENT_COPY.choose}
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-3">
              {/* Necessary row */}
              <div className="flex flex-col gap-1 rounded-lg border border-noir-700 bg-noir-900/60 p-3">
                <Switch
                  checked={true}
                  disabled={true}
                  onChange={() => {}}
                  label={CONSENT_COPY.necessaryTitle}
                  stateText={{ on: CONSENT_COPY.alwaysOn, off: CONSENT_COPY.off }}
                />
                <p className="text-[11px] text-sand-400 pl-10.5">{CONSENT_COPY.necessaryText}</p>
              </div>

              {/* Analytics row */}
              <div className="flex flex-col gap-1 rounded-lg border border-noir-700 bg-noir-900/60 p-3">
                <Switch
                  checked={analytics}
                  onChange={setAnalytics}
                  label={CONSENT_COPY.analyticsTitle}
                  stateText={{ on: CONSENT_COPY.on, off: CONSENT_COPY.off }}
                />
                <p className="text-[11px] text-sand-400 pl-10.5">{CONSENT_COPY.analyticsText}</p>
              </div>

              {/* Marketing row */}
              <div className="flex flex-col gap-1 rounded-lg border border-noir-700 bg-noir-900/60 p-3">
                <Switch
                  checked={marketing}
                  onChange={setMarketing}
                  label={CONSENT_COPY.marketingTitle}
                  stateText={{ on: CONSENT_COPY.on, off: CONSENT_COPY.off }}
                />
                <p className="text-[11px] text-sand-400 pl-10.5">{CONSENT_COPY.marketingText}</p>
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-1">
              <Button
                variant="primary"
                onClick={handleSaveChoices}
                className="w-full min-h-11 sm:w-auto"
              >
                {CONSENT_COPY.save}
              </Button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

export default ConsentBanner;
