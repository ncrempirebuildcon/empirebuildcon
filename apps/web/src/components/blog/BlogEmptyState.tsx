/**
 * BlogEmptyState component (Phase 5 Task 5.5b).
 *
 * Implements:
 *   - NoirBlog empty state with dashed gold border.
 *   - Heading: "Nothing in this category yet".
 *   - Lede: "We only publish when there is something useful to say. Try another category."
 *   - "Show all articles" link back to `/blog` (works without JavaScript).
 *   - 44px minimum tap target.
 */
import Link from "next/link";

export function BlogEmptyState() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-[20px] border border-dashed border-gold-400/50 p-10 text-center sm:p-14">
      <h2 className="font-serif text-xl font-semibold text-ivory sm:text-2xl">
        Nothing in this category yet
      </h2>
      <p className="max-w-md text-base text-body">
        We only publish when there is something useful to say. Try another category.
      </p>
      <Link
        href="/blog"
        className="mt-2 inline-flex min-h-[44px] items-center justify-center rounded-full bg-gold-500 px-6 py-3 text-sm font-extrabold text-noir-900 transition-colors hover:bg-gold-400 focus-visible:outline-2 focus-visible:outline-gold-300"
      >
        Show all articles
      </Link>
    </div>
  );
}

export default BlogEmptyState;
