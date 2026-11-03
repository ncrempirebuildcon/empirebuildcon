/**
 * ArticleHeader component for /blog/[slug] (Phase 5 Task 5.5b).
 *
 * Implements:
 *   - Breadcrumbs: Home / Blog / Category / Title.
 *   - Category eyebrow chip.
 *   - Single H1 in Cinzel metallic gradient, [text-wrap:balance].
 *   - Excerpt.
 *   - Author (only when non-null; initials avatar + name), Indian date in <time dateTime>, read time.
 *   - ShareLinks integration.
 */
import Link from "next/link";
import type { PublicPostDetail } from "@/lib/public/api";
import ShareLinks from "@/components/public/ShareLinks";
import { formatBlogDate } from "@/lib/blog/dates";
import { formatReadTime } from "@/lib/blog/readTime";

export interface ArticleHeaderProps {
  post: PublicPostDetail;
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  const first = parts[0];
  if (!first) return "";
  if (parts.length === 1) return first.slice(0, 2).toUpperCase();
  const last = parts[parts.length - 1];
  if (!last) return first.slice(0, 2).toUpperCase();
  const firstChar = first[0] ?? "";
  const lastChar = last[0] ?? "";
  return (firstChar + lastChar).toUpperCase();
}

export function ArticleHeader({ post }: ArticleHeaderProps) {
  const formattedDate = formatBlogDate(post.published_at);
  const readTime = formatReadTime(post.body);
  const initials = post.author ? getInitials(post.author) : "";

  return (
    <div className="flex flex-col gap-6">
      {/* Breadcrumbs with 44px min-h touch target */}
      <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-2 text-sm text-muted">
        <Link
          href="/"
          className="inline-flex min-h-11 items-center transition-colors hover:text-gold-300 focus-visible:outline-2 focus-visible:outline-gold-300"
        >
          Home
        </Link>
        <span aria-hidden="true">/</span>
        <Link
          href="/blog"
          className="inline-flex min-h-11 items-center transition-colors hover:text-gold-300 focus-visible:outline-2 focus-visible:outline-gold-300"
        >
          Blog
        </Link>
        {post.category && (
          <>
            <span aria-hidden="true">/</span>
            <Link
              href={`/blog?category=${encodeURIComponent(post.category)}`}
              className="inline-flex min-h-11 items-center transition-colors hover:text-gold-300 focus-visible:outline-2 focus-visible:outline-gold-300"
            >
              {post.category}
            </Link>
          </>
        )}
        <span aria-hidden="true">/</span>
        <span className="line-clamp-1 max-w-xs text-body sm:max-w-md">{post.title}</span>
      </nav>

      {/* Header section */}
      <section
        aria-label="Article heading"
        className="mx-auto flex max-w-[960px] flex-col items-center gap-4 text-center"
      >
        {post.category && (
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-gold-400/60 px-3 py-1 text-xs font-bold text-gold-300">
              {post.category}
            </span>
          </div>
        )}

        <h1 className="bg-gradient-to-b from-[#F8E7B0] via-[#E2B65A] to-[#C08A2E] bg-clip-text font-serif text-3xl font-semibold leading-tight text-transparent [text-wrap:balance] sm:text-4xl md:text-5xl lg:text-[54px]">
          {post.title}
        </h1>

        {post.excerpt && (
          <p className="max-w-[36em] text-base leading-relaxed text-body sm:text-lg md:text-[19px]">
            {post.excerpt}
          </p>
        )}

        {/* Metadata: Author, Date, Read Time */}
        <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-sm text-muted">
          {post.author ? (
            <span className="inline-flex items-center gap-2">
              <span
                aria-hidden="true"
                className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-line-strong bg-noir-700 text-xs font-extrabold text-gold-300"
              >
                {initials}
              </span>
              <span className="text-ivory">{post.author}</span>
            </span>
          ) : null}

          {post.published_at ? <time dateTime={post.published_at}>{formattedDate}</time> : null}

          <span>{readTime}</span>
        </div>

        {/* Share buttons */}
        <div className="pt-2">
          <ShareLinks title={post.title} url={`/blog/${post.slug}`} />
        </div>
      </section>
    </div>
  );
}

export default ArticleHeader;
