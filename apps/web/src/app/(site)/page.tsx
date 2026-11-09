/**
 * Home: the CMS's "home" page and its blocks (task 5.5a, D-045). Until that page is published
 * the holding content below stays, so the site never shows an empty home page.
 * Restyled with the approved Black & gold theme (D-033, D-038).
 */
import type { Metadata } from "next";
import Image from "next/image";
import { PageView } from "@/components/blocks/PageView";
import { firstImage, firstText } from "@/components/blocks/Blocks";
import { JsonLd } from "@/components/JsonLd";
import { fetchPublicPageOrNull, fetchPublicSite } from "@/lib/public/api";
import { organizationLd, pageMetadata } from "@/lib/public/seo";

export async function generateMetadata(): Promise<Metadata> {
  const page = await fetchPublicPageOrNull("home");
  // The site layout's default title stays until the home page is published.
  if (!page || page.blocks.length === 0) {
    const site = await fetchPublicSite();
    const meta = pageMetadata({
      title: site.company.name || "Empire",
      path: "/",
      fallbackDescriptions: [site.seo?.default_description, site.company.tagline],
      siteName: site.company.name || "Empire",
    });
    // The layout's default title (the site's own) stays.
    delete meta.title;
    return meta;
  }
  return {
    ...pageMetadata({
      title: page.title,
      path: "/",
      seo: page.seo,
      fallbackDescriptions: [firstText(page.blocks)],
      image: firstImage(page.blocks),
    }),
    // WHY absolute: the home page's title is the site's own, without the "· Empire" suffix.
    title: { absolute: page.seo?.title?.trim() || page.title },
  };
}

export default async function HomePage() {
  const [page, site] = await Promise.all([fetchPublicPageOrNull("home"), fetchPublicSite()]);
  // Organization structured data lives on the home page only (one per site).
  const org = <JsonLd data={organizationLd(site.company, site.social)} />;
  if (page && page.blocks.length > 0) {
    return (
      <>
        {org}
        <PageView page={page} path="/" />
      </>
    );
  }
  return (
    <>
      {org}
      <HoldingPage />
    </>
  );
}

function HoldingPage() {
  return (
    <section className="grid min-h-[60vh] place-items-center px-4 py-16">
      <div className="flex max-w-xl flex-col items-center gap-5 text-center">
        <Image
          src="/brand/logo-stacked-noir.webp"
          alt="Empire Buildcon — Delivering Happiness"
          width={320}
          height={230}
          priority
          unoptimized
          className="h-auto w-[min(320px,80vw)]"
        />
        <h1 className="font-display text-[clamp(26px,5vw,38px)] leading-tight font-semibold tracking-wide text-metallic">
          Our new website is on its way
        </h1>
        <div className="star-rule w-56 text-xs" aria-hidden="true">
          ✦
        </div>
        <p className="text-lede text-body">
          We&apos;re building a home online for Empire&apos;s projects. Please check back soon.
        </p>
        <p className="text-caption text-muted">empirebuildcon.com</p>
      </div>
    </section>
  );
}
