/**
 * Public Blog article detail page (Phase 5 Task 5.5b).
 *
 * Implements:
 *   - Fetches post by slug via fetchPublicPost(slug); calls notFound() if not found or unpublished.
 *   - Metadata title from post.seo.title || post.title.
 *   - ArticleHeader with breadcrumbs, category, single H1, excerpt, author, date, read time, and share.
 *   - Cover image via PublicImage with honest label.
 *   - Article body rendered with FormattedText (never HTML).
 *   - Tags displayed as text chips.
 *   - Bottom share bar.
 *   - Accessible and responsive without horizontal scroll at 390px.
 */
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { fetchPublicPost, type PublicPostDetail } from "@/lib/public/api";
import { FormattedText } from "@empire/ui";
import PublicImage from "@/components/media/PublicImage";
import ArticleHeader from "@/components/blog/ArticleHeader";
import ShareLinks from "@/components/public/ShareLinks";

interface BlogSlugPageProps {
  params: Promise<{ slug: string }>;
}

export async function generateMetadata({ params }: BlogSlugPageProps): Promise<Metadata> {
  const { slug } = await params;
  try {
    const post = await fetchPublicPost(slug);
    const title = post.seo?.title || post.title;
    return {
      title: { absolute: `${title} · Empire` },
      description: post.seo?.description || post.excerpt || undefined,
    };
  } catch {
    return {
      title: { absolute: "Article not found · Empire" },
    };
  }
}

export default async function BlogSlugPage({ params }: BlogSlugPageProps) {
  const { slug } = await params;

  let post: PublicPostDetail;
  try {
    post = await fetchPublicPost(slug);
  } catch {
    notFound();
  }

  return (
    <div className="mx-auto flex max-w-[1280px] flex-col gap-8 px-4 py-8 sm:px-8 sm:py-10 md:gap-10">
      {/* Article Header (Breadcrumbs, title H1, excerpt, author, date, read time, share) */}
      <ArticleHeader post={post} />

      {/* Cover image */}
      {post.cover?.url && (
        <div className="mx-auto w-full max-w-[1120px]">
          <div className="relative aspect-16/10 max-h-[540px] w-full overflow-hidden rounded-t-[999px] rounded-b-[18px] border border-gold-line bg-noir-800">
            <PublicImage
              src={post.cover.url}
              alt={post.cover.alt_text || post.title}
              label={post.cover.label}
              labelMonth={post.cover.label_month}
              isSample={post.cover.is_sample}
              fill
              priority
              className="object-cover"
              containerClassName="w-full h-full"
            />
          </div>
        </div>
      )}

      {/* Article Body & Tags */}
      <div className="mx-auto flex w-full max-w-[800px] flex-col gap-8 py-4 sm:py-6">
        <article className="flex flex-col gap-6 text-base leading-[1.75] text-body sm:text-lg sm:leading-[1.8]">
          <FormattedText text={post.body} />
        </article>

        {/* Tags */}
        {post.tags && post.tags.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 border-t border-line pt-6">
            <span className="text-xs font-bold uppercase tracking-wider text-muted">Tags:</span>
            {post.tags.map((tag) => (
              <span
                key={tag}
                className="rounded-md border border-line bg-noir-800 px-2.5 py-1 text-xs text-body"
              >
                #{tag}
              </span>
            ))}
          </div>
        )}

        {/* Bottom share bar */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-line pt-6">
          <span className="text-sm font-semibold text-ivory">Share this article:</span>
          <ShareLinks title={post.title} url={`/blog/${post.slug}`} />
        </div>
      </div>
    </div>
  );
}
