"use client";

/**
 * Keeps the landing address's UTM tags and click IDs for this browser tab (first touch), on
 * every page of the public site, so a lead sent later from another page still carries them
 * (task 5.4, D-043; ARCHITECTURE §8). Renders nothing.
 *
 * Privacy: session storage only (no cookie), only the known keys (lib/public/leads.ts), and
 * nothing is sent anywhere until the visitor sends a form.
 */
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { captureAttribution } from "@/lib/public/leads";

export function AttributionCapture() {
  // WHY the pathname: a client-side navigation to a tagged address runs this again.
  const pathname = usePathname();
  useEffect(() => {
    let storage: Storage | null = null;
    try {
      storage = window.sessionStorage;
    } catch {
      storage = null;
    }
    captureAttribution(window.location.search, storage);
  }, [pathname]);
  return null;
}

export default AttributionCapture;
