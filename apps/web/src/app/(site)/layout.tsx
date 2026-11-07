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
import type { Metadata } from "next";
import type { ReactNode } from "react";
import Header from "@/components/shell/Header";
import Footer from "@/components/shell/Footer";
import MobileActionBar from "@/components/shell/MobileActionBar";
import OfferBanner from "@/components/shell/OfferBanner";
import SampleDataRibbon from "@/components/shell/SampleDataRibbon";
import AttributionCapture from "@/components/leads/AttributionCapture";
import { ConsentBanner } from "@/components/consent/ConsentBanner";
import { fetchPublicSite, type PublicSite } from "@/lib/public/api";

export const dynamic = "force-dynamic";

/**
 * Site-wide title and description from the CMS's SEO defaults (task 5.6, D-047). Pages set their
 * own title; the suffix ("· Empire") comes from here.
 */
export async function generateMetadata(): Promise<Metadata> {
  let site: PublicSite | undefined;
  try {
    site = await fetchPublicSite();
  } catch {
    return {};
  }
  const name = site.company.name || "Empire";
  const suffix = site.seo?.title_suffix?.trim();
  const fallbackTitle = site.company.tagline ? `${name} · ${site.company.tagline}` : name;
  return {
    title: {
      default: site.seo?.default_title?.trim() || fallbackTitle,
      template: suffix ? `%s ${suffix}` : `%s · ${name}`,
    },
    description: site.seo?.default_description?.trim() || site.company.tagline || undefined,
  };
}

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

  // Phase 6 Task 6.1 (D-056): Consent banner & cookie settings only when tracking IDs exist
  const trackingEnabled = Boolean(
    site?.tracking && (site.tracking.gtm_id || site.tracking.ga4_id || site.tracking.meta_pixel_id),
  );

  return (
    <div className="flex min-h-dvh flex-col bg-noir-900 text-body">
      {/* WHY first: the sample ribbon and offer banner above the header can hold links, and
          keyboard users must reach "Skip to content" with their first Tab (task 5.7). */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 inline-flex min-h-11 items-center focus:rounded-full focus:bg-gold-500 focus:px-4 focus:text-sm focus:font-extrabold focus:text-noir-900 focus:shadow-lg focus:outline-2 focus:outline-gold-200"
      >
        Skip to content
      </a>
      <AttributionCapture />
      <SampleDataRibbon hasSampleData={hasSample} />
      {site?.offers && <OfferBanner offers={site.offers} />}
      <Header site={site} isProduction={isProd} />
      {/* tabIndex -1: the skip link moves focus here, so the next Tab starts inside main. */}
      <main id="main-content" tabIndex={-1} className="flex-1 scroll-mt-24 outline-none">
        {children}
      </main>
      <Footer site={site} isProduction={isProd} trackingEnabled={trackingEnabled} />
      <ConsentBanner enabled={trackingEnabled} />
      <MobileActionBar company={site?.company} isProduction={isProd} />
    </div>
  );
}
