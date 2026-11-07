"use client";
/**
 * Footer action button to re-open the Cookie choices / settings banner (Phase 6 Task 6.1).
 */
import { openConsentSettings } from "@/lib/consent";

export function CookieSettingsButton() {
  return (
    <button
      type="button"
      onClick={() => openConsentSettings()}
      className="inline-flex min-h-11 min-w-11 items-center justify-center hover:text-sand-200"
    >
      Cookie settings
    </button>
  );
}

export default CookieSettingsButton;
