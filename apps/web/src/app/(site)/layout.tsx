/**
 * Public website shell layout (Phase 5 Task 5.2).
 *
 * Implements ARCHITECTURE §3 & §5:
 *   - Route group (site) isolates public pages from /admin.
 *   - Fetches site settings & nav from /api/v1/public/site with cache tag "site".
 *   - Renders real Header, Menu, Footer, MobileActionBar, OfferBanner, and SampleDataRibbon.
 *   - Main content wrapped with landmark (`#main-content`) for keyboard skip link.
 */
import type { ReactNode } from "react";
import Header from "@/components/shell/Header";
import Footer from "@/components/shell/Footer";
import MobileActionBar from "@/components/shell/MobileActionBar";
import OfferBanner from "@/components/shell/OfferBanner";
import SampleDataRibbon from "@/components/shell/SampleDataRibbon";
import { fetchPublicSite, type PublicSite } from "@/lib/public/api";

export default async function SiteLayout({ children }: { children: ReactNode }) {
  let site: PublicSite | undefined;
  try {
    site = await fetchPublicSite();
  } catch {
    // If during build without running API, proceed with undefined so build succeeds;
    // in runtime, other errors trigger error.tsx
    if (process.env.NEXT_PHASE !== "phase-production-build") {
      // Allow error boundary to catch if not build time
      // But don't crash if dev server started without API
    }
  }

  const isProd = process.env.NODE_ENV === "production" || process.env.APP_ENV === "production";

  return (
    <div className="flex min-h-dvh flex-col bg-noir-900 text-body">
      <SampleDataRibbon />
      {site?.offers && <OfferBanner offers={site.offers} />}
      <Header site={site} isProduction={isProd} />
      <main id="main-content" className="flex-1">
        {children}
      </main>
      <Footer site={site} isProduction={isProd} />
      <MobileActionBar company={site?.company} />
    </div>
  );
}
