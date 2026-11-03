/**
 * /<slug>: any published page-builder page that isn't home (About, legal, standard and
 * campaign landing pages; task 5.5a, D-045). Unknown, draft and archived pages are the site's
 * 404 (the API answers 404; the data layer calls `notFound()`).
 *
 * The site's own sections (/projects, /properties, /blog, /contact, /cities …) are their own
 * routes and win over this one; their slugs are reserved for pages in the CMS (seo/paths.py).
 */
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PageView } from "@/components/blocks/PageView";
import { firstImage, firstText } from "@/components/blocks/Blocks";
import { fetchPublicPage } from "@/lib/public/api";
import { pageMetadata } from "@/lib/public/seo";

type Params = { params: Promise<{ slug: string }> };

// WHY: the home page lives at "/" only; "/home" would be a duplicate of it.
const HOME_SLUG = "home";

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const slug = (await params).slug;
  if (slug === HOME_SLUG) notFound();
  const page = await fetchPublicPage(slug);
  return pageMetadata({
    title: page.title,
    path: `/${page.slug}`,
    seo: page.seo,
    fallbackDescriptions: [firstText(page.blocks)],
    image: firstImage(page.blocks),
    // Campaign landing pages are never indexed (D-035); the rest follows the site-wide rule.
    noindex: page.kind === "landing",
  });
}

export default async function SitePage({ params }: Params) {
  const { slug } = await params;
  if (slug === HOME_SLUG) notFound();
  const page = await fetchPublicPage(slug);
  return <PageView page={page} path={`/${slug}`} />;
}
