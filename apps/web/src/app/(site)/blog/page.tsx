/**
 * Public Blog listing page (Phase 5 Task 5.5b).
 *
 * Implements:
 *   - Heading and intro matching NoirBlog.
 *   - Featured post on page 1 with no filter only.
 *   - Category chips with "All" first; active chip marked with aria-current.
 *   - Card grid with PublicImage cover, honest label, title H2, excerpt, date, read time.
 *   - Server-rendered pagination working without JavaScript.
 *   - Empty state on empty category or page number past the end.
 *   - Accessible: single link per card, 44px min tap targets, visible focus.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { fetchPublicPosts, type PublicPostList } from "@/lib/public/api";
import CategoryChips from "@/components/blog/CategoryChips";
import FeaturedPostCard from "@/components/blog/FeaturedPostCard";
import PostCard from "@/components/blog/PostCard";
import BlogPagination from "@/components/blog/BlogPagination";
import BlogEmptyState from "@/components/blog/BlogEmptyState";

export const metadata: Metadata = {
  title: { absolute: "News & guides · Empire" },
  description:
    "Plain-language guides for home buyers, dated construction updates from our sites, and company news.",
};

interface BlogPageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export default async function BlogPage({ searchParams }: BlogPageProps) {
  const resolvedParams = await searchParams;

  // Parse page number
  const rawPage = Array.isArray(resolvedParams.page) ? resolvedParams.page[0] : resolvedParams.page;
  const pageNum = Math.max(1, parseInt(rawPage || "1", 10) || 1);

  // Parse category filter
  const rawCat = Array.isArray(resolvedParams.category)
    ? resolvedParams.category[0]
    : resolvedParams.category;
  const activeCategory =
    rawCat && rawCat.trim().toLowerCase() !== "all" ? rawCat.trim() : undefined;

  // 1. Fetch categories list (up to max API limit 100, cached under "posts")
  let categories: string[] = [];
  try {
    const allPostsRes = await fetchPublicPosts({ per_page: 100 });
    const categorySet = new Set<string>();
    for (const post of allPostsRes.items) {
      if (post.category && post.category.trim()) {
        categorySet.add(post.category.trim());
      }
    }
    categories = Array.from(categorySet).sort((a, b) => a.localeCompare(b));
  } catch {
    categories = [];
  }

  // 2. Fetch current page of posts (per_page = 9 for 3-column grid)
  let posts: PublicPostList;
  try {
    posts = await fetchPublicPosts({
      page: pageNum,
      per_page: 9,
      category: activeCategory,
    });
  } catch {
    posts = {
      items: [],
      meta: { page: pageNum, per_page: 9, total: 0, pages: 0 },
    };
  }

  const isPageOneNoCategory = pageNum === 1 && !activeCategory;
  const hasPosts = posts.items.length > 0;

  // Featured post is the 1st post on page 1 with no category filter only
  const featuredPost = isPageOneNoCategory && hasPosts ? posts.items[0] : null;
  const gridPosts = isPageOneNoCategory && hasPosts ? posts.items.slice(1) : posts.items;

  return (
    <div className="mx-auto flex max-w-[1280px] flex-col gap-8 px-4 py-8 sm:px-8 sm:py-10 md:gap-10">
      {/* Breadcrumb */}
      <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-sm text-muted">
        <Link
          href="/"
          className="transition-colors hover:text-gold-300 focus-visible:outline-2 focus-visible:outline-gold-300"
        >
          Home
        </Link>
        <span aria-hidden="true">/</span>
        <span className="text-body">Blog</span>
      </nav>

      {/* Heading & intro */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-2">
          <p className="font-serif text-xs font-semibold uppercase tracking-[0.28em] text-gold-400">
            BLOG
          </p>
          <h1 className="bg-gradient-to-b from-[#F8E7B0] via-[#E2B65A] to-[#C08A2E] bg-clip-text font-serif text-4xl font-semibold leading-tight text-transparent sm:text-5xl lg:text-[54px]">
            News &amp; guides
          </h1>
        </div>
        <p className="max-w-[34em] text-base leading-relaxed text-body">
          Plain-language guides for home buyers, dated construction updates from our sites, and
          company news.
        </p>
      </div>

      {/* Featured post (Page 1 without filter only) */}
      {featuredPost && <FeaturedPostCard post={featuredPost} />}

      {/* Articles section */}
      <section aria-label="Articles" className="flex flex-col gap-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <CategoryChips categories={categories} activeCategory={activeCategory} />
          {hasPosts && (
            <p className="text-sm text-muted">
              <strong className="text-ivory">{posts.meta.total}</strong>{" "}
              {posts.meta.total === 1 ? "article" : "articles"} · newest first
            </p>
          )}
        </div>

        {hasPosts ? (
          <>
            {gridPosts.length > 0 && (
              <div className="grid grid-cols-1 gap-7 sm:grid-cols-2 lg:grid-cols-3">
                {gridPosts.map((post) => (
                  <PostCard key={post.id} post={post} />
                ))}
              </div>
            )}
            <BlogPagination
              currentPage={posts.meta.page}
              totalPages={posts.meta.pages}
              category={activeCategory}
            />
          </>
        ) : (
          <BlogEmptyState />
        )}
      </section>
    </div>
  );
}
