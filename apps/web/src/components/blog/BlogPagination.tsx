/**
 * BlogPagination component (Phase 5 Task 5.5b).
 *
 * Implements:
 *   - Plain links `<a href="...">` working without JavaScript.
 *   - Previous, Next, and page numbers.
 *   - `aria-current="page"` on current page link.
 *   - Preserves category filter in query string.
 *   - 44px minimum tap targets.
 */
import Link from "next/link";
import { buildPaginationHref } from "@/lib/blog/links";

export interface BlogPaginationProps {
  currentPage: number;
  totalPages: number;
  category?: string | null;
}

export function BlogPagination({ currentPage, totalPages, category }: BlogPaginationProps) {
  if (totalPages <= 1) return null;

  const pages = Array.from({ length: totalPages }, (_, i) => i + 1);

  return (
    <nav
      aria-label="Pagination"
      className="mt-4 flex flex-wrap items-center justify-center gap-2 text-sm font-bold"
    >
      {/* Previous button */}
      {currentPage > 1 ? (
        <Link
          href={buildPaginationHref(currentPage - 1, { category })}
          aria-label="Previous page"
          className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-full border border-gold-line px-3.5 text-gold-300 transition-colors hover:border-gold-500 focus-visible:outline-2 focus-visible:outline-gold-300"
        >
          ‹
        </Link>
      ) : (
        <span
          aria-hidden="true"
          className="inline-flex min-h-[44px] min-w-[44px] cursor-not-allowed items-center justify-center rounded-full border border-line text-muted opacity-40"
        >
          ‹
        </span>
      )}

      {/* Page numbers */}
      {pages.map((p) => {
        const isCurrent = p === currentPage;
        return (
          <Link
            key={p}
            href={buildPaginationHref(p, { category })}
            aria-current={isCurrent ? "page" : undefined}
            className={`inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-full px-3 text-sm font-bold transition-colors focus-visible:outline-2 focus-visible:outline-gold-300 ${
              isCurrent
                ? "bg-gold-500 font-extrabold text-noir-900"
                : "border border-line-strong text-ivory hover:border-gold-line hover:text-gold-300"
            }`}
          >
            {p}
          </Link>
        );
      })}

      {/* Next button */}
      {currentPage < totalPages ? (
        <Link
          href={buildPaginationHref(currentPage + 1, { category })}
          aria-label="Next page"
          className="inline-flex min-h-[44px] items-center justify-center rounded-full border border-gold-400 px-4 text-gold-300 transition-colors hover:bg-gold-500/10 focus-visible:outline-2 focus-visible:outline-gold-300"
        >
          Next ›
        </Link>
      ) : (
        <span
          aria-hidden="true"
          className="inline-flex min-h-[44px] min-w-[44px] cursor-not-allowed items-center justify-center rounded-full border border-line text-muted opacity-40"
        >
          ›
        </span>
      )}
    </nav>
  );
}

export default BlogPagination;
