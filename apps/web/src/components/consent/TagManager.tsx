"use client";
/**
 * Runs the tags the visitor's cookie choice allows (task 6.3, D-058). Renders nothing.
 *
 * - No choice yet → nothing loads (the banner asks).
 * - A choice → `applyConsent` loads what it allows, then a page view is sent, and one more on
 *   every client-side navigation.
 * - A narrower choice after a tag loaded → the page reloads (tags can't be unloaded).
 * - A sent enquiry (the "empire:lead" event from LeadForm) → `trackLead`.
 * Mounted only when the layout found usable IDs (lib/tracking/platforms.ts).
 */
import { usePathname } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import { readConsent, subscribe } from "@/lib/consent";
import type { TrackingIds } from "@/lib/tracking/platforms";
import { LEAD_EVENT_NAME, type LeadEventDetail } from "@/lib/tracking/events";
import { applyConsent, needsReload, trackLead, trackPageView } from "@/lib/tracking/tags";

export function TagManager({ ids }: { ids: TrackingIds }) {
  const consent = useSyncExternalStore(subscribe, readConsent, () => null);
  const pathname = usePathname();

  useEffect(() => {
    if (needsReload(consent)) {
      window.location.reload();
      return;
    }
    if (consent) applyConsent(consent, ids);
  }, [consent, ids]);

  useEffect(() => {
    if (consent) trackPageView(ids);
  }, [pathname, consent, ids]);

  useEffect(() => {
    const onLead = (event: Event) => {
      const reference = (event as CustomEvent<LeadEventDetail>).detail?.reference;
      if (reference) trackLead(ids, reference);
    };
    window.addEventListener(LEAD_EVENT_NAME, onLead);
    return () => window.removeEventListener(LEAD_EVENT_NAME, onLead);
  }, [ids]);

  return null;
}

export default TagManager;
