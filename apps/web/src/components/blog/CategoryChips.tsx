/**
 * CategoryChips component for the blog listing (Phase 5 Task 5.5b).
 *
 * Implements:
 *   - "All" first, followed by distinct categories.
 *   - Plain links `<a href="...">` working without JavaScript.
 *   - Active chip has `aria-current="page"`.
 *   - Matches exact category text with API filter.
 *   - Changing category drops `page` parameter.
 *   - Min 44px touch targets.
 */
import Link from "next/link";
import { buildCategoryHref } from "@/lib/blog/links";

export interface CategoryChipsProps {
  categories: string[];
  activeCategory?: string | null;
}

export function CategoryChips({ categories, activeCategory }: CategoryChipsProps) {
  const isAllActive = !activeCategory || activeCategory.trim().toLowerCase() === "all";

  return (
    <nav
      aria-label="Category"
      className="inline-flex max-w-full flex-wrap gap-1.5 rounded-full border border-line bg-noir-800 p-1.5"
    >
      {/* "All" chip */}
      <Link
        href={buildCategoryHref("all")}
        aria-current={isAllActive ? "page" : undefined}
        className={`inline-flex min-h-[44px] items-center justify-center rounded-full px-4 py-2 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-gold-300 ${
          isAllActive ? "bg-gold-500 font-extrabold text-noir-900" : "text-body hover:text-gold-300"
        }`}
      >
        All
      </Link>

      {/* Individual category chips (exact match with API) */}
      {categories.map((cat) => {
        const isActive = !isAllActive && activeCategory === cat;

        return (
          <Link
            key={cat}
            href={buildCategoryHref(cat)}
            aria-current={isActive ? "page" : undefined}
            className={`inline-flex min-h-[44px] items-center justify-center rounded-full px-4 py-2 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-gold-300 ${
              isActive
                ? "bg-gold-500 font-extrabold text-noir-900"
                : "text-body hover:text-gold-300"
            }`}
          >
            {cat}
          </Link>
        );
      })}
    </nav>
  );
}

export default CategoryChips;
