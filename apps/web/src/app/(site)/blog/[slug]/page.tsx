/**
 * Public Blog article detail page (Phase 5 Task 5.5b).
 *
 * Implements:
 *   - Fetches post by slug via fetchPublicPost(slug); data layer calls notFound() on 404.
 *   - Metadata title from post.seo.title || post.title (description out of scope until 5.6).
 *   - ArticleHeader with breadcrumbs, category, single H1, excerpt, author, date, read time, and share.
 *   - Cover image via PublicImage with honest label.
 *   - Article body rendered with FormattedText (never HTML).
 *   - Tags displayed as text chips.
 *   - Bottom share bar.
 *   - Accessible and responsive without horizontal scroll at 390px.
 */
import type { Metadata } from "next";
import { fetchPublicPost } from "@/lib/public/api";
import { FormattedText } from "@empire/ui";
import PublicImage from "@/components/media/PublicImage";
import ArticleHeader from "@/components/blog/ArticleHeader";
import ShareLinks from "@/components/public/ShareLinks";

interface BlogSlugPageProps {
  params: Promise<{ slug: string }>;
}

export async function generateMetadata({ params }: BlogSlugPageProps): Promise<Metadata> {
  const { slug } = await params;
  const post = await fetchPublicPost(slug);
  const title = post.seo?.title || post.title;
  return {
    title: { absolute: `${title} · Empire` },
  };
}

export default async function BlogSlugPage({ params }: BlogSlugPageProps) {
  const { slug } = await params;
  const post = await fetchPublicPost(slug);

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

      {/* Article body */}
      <article className="prose prose-invert mx-auto w-full max-w-[760px] text-body">
        <FormattedText text={post.body} />
      </article>

      {/* Tags section */}
      {post.tags && post.tags.length > 0 && (
        <div className="mx-auto flex w-full max-w-[760px] flex-wrap items-center gap-2 pt-4">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted">Tags:</span>
          {post.tags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center rounded-full border border-line bg-noir-800 px-3 py-1 text-xs text-muted"
            >
              #{tag}
            </span>
          ))}
        </div>
      )}

      {/* Bottom share bar */}
      <div className="mx-auto flex w-full max-w-[760px] flex-col gap-3 border-t border-line pt-8">
        <p className="font-serif text-sm font-semibold uppercase tracking-wider text-gold-400">
          Share this article
        </p>
        <ShareLinks url={`/blog/${post.slug}`} title={post.title} />
      </div>
    </div>
  );
}
