/**
 * Standard PostCard component for blog grid (Phase 5 Task 5.5b).
 *
 * Implements:
 *   - The card is one link (no nested links), with the title as its accessible name.
 *   - Cover image via PublicImage with alt text and honest label.
 *   - Aspect ratio 16/10 with design-system arch radius (rounded-t-[999px] rounded-b-[10px]).
 *   - Category, title H2, excerpt, Indian date in <time dateTime>, read time.
 *   - 44px min tap target, visible focus outline.
 */
import Link from "next/link";
import type { PublicPostDetail } from "@/lib/public/api";
import PublicImage from "@/components/media/PublicImage";
import { formatBlogDate } from "@/lib/blog/dates";
import { formatReadTime } from "@/lib/blog/readTime";

export interface PostCardProps {
  post: PublicPostDetail;
}

export function PostCard({ post }: PostCardProps) {
  const formattedDate = formatBlogDate(post.published_at);
  const readTime = formatReadTime(post.body);

  return (
    <article className="group relative flex h-full flex-col overflow-hidden rounded-[22px] border border-gold-line bg-noir-800 text-body transition-colors hover:border-gold-line-strong focus-within:border-gold-500/60">
      {post.cover?.url ? (
        <div className="relative p-3.5 pb-0">
          <div className="relative aspect-16/10 w-full overflow-hidden rounded-t-[999px] rounded-b-[10px]">
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
        </div>
      ) : (
        <div className="p-3.5 pb-0">
          <div className="aspect-16/10 w-full rounded-t-[999px] rounded-b-[10px] border border-line bg-noir-700" />
        </div>
      )}

      <div className="flex flex-1 flex-col gap-2.5 p-5">
        {post.category && (
          <span className="font-serif text-xs font-semibold uppercase tracking-[0.18em] text-gold-400">
            {post.category}
          </span>
        )}

        <h2 className="font-serif text-[22px] font-semibold leading-snug text-ivory transition-colors group-hover:text-gold-300">
          <Link
            href={`/blog/${post.slug}`}
            className="before:absolute before:inset-0 before:z-10 focus:outline-none focus-visible:outline-2 focus-visible:outline-gold-300"
          >
            {post.title}
          </Link>
        </h2>

        {post.excerpt && (
          <p className="line-clamp-3 text-[15px] leading-relaxed text-body">{post.excerpt}</p>
        )}

        <p className="mt-auto border-t border-line pt-2.5 text-[13px] text-muted">
          {post.published_at ? <time dateTime={post.published_at}>{formattedDate}</time> : null}
          {formattedDate ? " · " : ""}
          {readTime}
        </p>
      </div>
    </article>
  );
}

export default PostCard;
