/**
 * /<slug>: any published page-builder page that isn't home (About, legal, standard and
 * campaign landing pages; task 5.5a, D-045). Unknown, draft and archived pages are the site's
 * 404 (the API answers 404; the data layer calls `notFound()`).
 *
 * The site's own sections (/projects, /properties, /blog, /contact, /cities …) are their own
 * routes and win over this one; their slugs are reserved for pages in the CMS (seo/paths.py).
 */
import type { Metadata } from "next";
import { PageView } from "@/components/blocks/PageView";
import { fetchPublicPage } from "@/lib/public/api";

type Params = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const page = await fetchPublicPage((await params).slug);
  return {
    title: page.seo?.title || page.title,
    // Campaign landing pages are never indexed (D-035); the rest follows the site-wide rule.
    ...(page.kind === "landing" || page.seo?.noindex
      ? { robots: { index: false, follow: false } }
      : {}),
  };
}

export default async function SitePage({ params }: Params) {
  const { slug } = await params;
  const page = await fetchPublicPage(slug);
  return <PageView page={page} path={`/${slug}`} />;
}
