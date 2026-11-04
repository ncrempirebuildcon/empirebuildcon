/**
 * Large FeaturedPostCard component for the top of page 1 (Phase 5 Task 5.5b).
 *
 * Implements:
 *   - Only rendered on page 1 with no category filter.
 *   - The card is one link (no nested links), with the title as its accessible name.
 *   - Cover image via PublicImage with alt text and honest label (16/10 aspect ratio).
 *   - Featured category badge, Cinzel H2 title, excerpt.
 *   - Author (only when provided; never invented), Indian date in <time dateTime>, read time.
 *   - 44px min tap target and visible focus ring.
 */
import Link from "next/link";
import type { PublicPostDetail } from "@/lib/public/api";
import PublicImage from "@/components/media/PublicImage";
import { formatBlogDate } from "@/lib/blog/dates";
import { formatReadTime } from "@/lib/blog/readTime";

export interface FeaturedPostCardProps {
  post: PublicPostDetail;
}

export function FeaturedPostCard({ post }: FeaturedPostCardProps) {
  const formattedDate = formatBlogDate(post.published_at);
  const readTime = formatReadTime(post.body);

  const badgeText = post.category ? `Featured · ${post.category}` : "Featured";

  return (
    <article
      data-testid="featured-post-card"
      className="group relative flex flex-col overflow-hidden rounded-[24px] border border-gold-line-strong bg-noir-800 text-body transition-colors hover:border-gold-500/60 focus-within:border-gold-500 md:flex-row"
    >
      {/* Cover image side */}
      <div className="w-full p-4 md:w-1/2 md:p-5">
        {post.cover?.url ? (
          <div className="relative aspect-16/10 w-full overflow-hidden rounded-t-[999px] rounded-b-[14px]">
            <PublicImage
              src={post.cover.url}
              alt={post.cover.alt_text || post.title}
              label={post.cover.label}
              labelMonth={post.cover.label_month}
              isSample={post.cover.is_sample}
              fill
              className="object-cover transition-transform duration-300 group-hover:scale-105"
              containerClassName="w-full h-full"
            />
          </div>
        ) : (
          <div className="aspect-16/10 w-full rounded-t-[999px] rounded-b-[14px] border border-line bg-noir-700" />
        )}
      </div>

      {/* Content side */}
      <div className="flex w-full flex-col justify-center gap-3.5 p-6 md:w-1/2 md:p-8 lg:p-10">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-gold-400/60 px-3 py-1 text-xs font-bold text-gold-300">
            {badgeText}
          </span>
        </div>

        <h2 className="font-serif text-2xl font-semibold leading-tight text-ivory transition-colors group-hover:text-gold-300 sm:text-3xl lg:text-[34px]">
          <Link
            href={`/blog/${post.slug}`}
            className="before:absolute before:inset-0 before:z-10 focus:outline-none focus-visible:outline-2 focus-visible:outline-gold-300"
          >
            {post.title}
          </Link>
        </h2>

        {post.excerpt && (
          <p className="line-clamp-3 text-base leading-relaxed text-body md:text-[17px]">
            {post.excerpt}
          </p>
        )}

        <p className="text-sm text-muted">
          {post.author ? <span>{post.author} · </span> : null}
          {post.published_at ? <time dateTime={post.published_at}>{formattedDate}</time> : null}
          {formattedDate ? " · " : ""}
          <span>{readTime}</span>
        </p>

        <span className="mt-2 inline-flex items-center self-start rounded-full bg-gold-500 px-5 py-3 text-sm font-extrabold text-noir-900 transition-colors group-hover:bg-gold-400">
          Read article
        </span>
      </div>
    </article>
  );
}

export default FeaturedPostCard;
