/**
 * Public website shell layout (Phase 5 Task 5.2, S6, S7, N7).
 *
 * Implements ARCHITECTURE §3, §5, D-038 & D-039:
 *   - Route group (site) isolates public pages from /admin.
 *   - Fetches site settings & nav from /api/v1/public/site with cache tag "site".
 *   - Rethrows errors at runtime (N7); only tolerates build phase without API.
 *   - Passes `isProduction` derived from APP_ENV to shell components (S6, S7).
 *   - Passes `hasSampleData` to SampleDataRibbon (S7).
 *   - Main content wrapped with landmark (`#main-content`) for keyboard skip link.
 *   - Shell padded at bottom for mobile action bar: `pb-[calc(64px+env(safe-area-inset-bottom))] md:pb-0` (S6).
 */
import type { ReactNode } from "react";
import Header from "@/components/shell/Header";
import Footer from "@/components/shell/Footer";
import MobileActionBar from "@/components/shell/MobileActionBar";
import OfferBanner from "@/components/shell/OfferBanner";
import SampleDataRibbon from "@/components/shell/SampleDataRibbon";
import AttributionCapture from "@/components/leads/AttributionCapture";
import { fetchPublicSite, type PublicSite } from "@/lib/public/api";

export const dynamic = "force-dynamic";

export default async function SiteLayout({ children }: { children: ReactNode }) {
  let site: PublicSite | undefined;
  try {
    site = await fetchPublicSite();
  } catch (err) {
    // N7: Only tolerate missing API during the build phase; at runtime rethrow so error boundary catches
    if (process.env.NEXT_PHASE === "phase-production-build") {
      site = undefined;
    } else {
      throw err;
    }
  }

  // S7: Determine production strictly from APP_ENV
  const isProd = process.env.APP_ENV === "production";

  // S7, S-N4: Detect whether current site payload contains sample items
  const hasSample = !isProd && Boolean(site?.has_sample);

  return (
    <div className="flex min-h-dvh flex-col bg-noir-900 text-body">
      <AttributionCapture />
      <SampleDataRibbon hasSampleData={hasSample} />
      {site?.offers && <OfferBanner offers={site.offers} />}
      <Header site={site} isProduction={isProd} />
      <main id="main-content" className="flex-1">
        {children}
      </main>
      <Footer site={site} isProduction={isProd} />
      <MobileActionBar company={site?.company} isProduction={isProd} />
    </div>
  );
}
