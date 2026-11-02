/**
 * URL and query string builders for blog category filtering and pagination (Phase 5 Task 5.5b).
 *
 * Rules:
 *   - Changing category drops `page` (always resets to page 1).
 *   - Changing page keeps the current `category` filter if active.
 *   - All parameter values are properly URL-encoded.
 *   - Selecting "All" (or null/undefined) drops the category parameter.
 *   - Page 1 omits the `page` parameter for canonical clean URLs.
 */

export interface BlogFilterParams {
  category?: string | null;
  page?: number | string | null;
}

/**
 * Builds the href for a category chip.
 * Drops the `page` parameter so changing category always starts at page 1.
 */
export function buildCategoryHref(
  newCategory: string | null | undefined,
  currentParams?: BlogFilterParams,
): string {
  void currentParams; // Explicitly ignored: switching category always drops the page parameter
  if (!newCategory || !newCategory.trim() || newCategory.trim().toLowerCase() === "all") {
    return "/blog";
  }
  const cleanCat = newCategory.trim();
  const searchParams = new URLSearchParams();
  searchParams.set("category", cleanCat);
  return `/blog?${searchParams.toString()}`;
}

/**
 * Builds the href for a pagination link (page number, previous, next).
 * Keeps the current `category` filter if present.
 */
export function buildPaginationHref(targetPage: number, currentParams?: BlogFilterParams): string {
  const searchParams = new URLSearchParams();

  if (currentParams?.category) {
    const cleanCat = currentParams.category.trim();
    if (cleanCat && cleanCat.toLowerCase() !== "all") {
      searchParams.set("category", cleanCat);
    }
  }

  if (targetPage > 1) {
    searchParams.set("page", String(targetPage));
  }

  const query = searchParams.toString();
  return query ? `/blog?${query}` : "/blog";
}

/**
 * Generic query builder for blog URLs.
 */
export function buildBlogHref(params: BlogFilterParams): string {
  const searchParams = new URLSearchParams();

  if (params.category) {
    const cleanCat = params.category.trim();
    if (cleanCat && cleanCat.toLowerCase() !== "all") {
      searchParams.set("category", cleanCat);
    }
  }

  const pageNum = Number(params.page);
  if (pageNum > 1) {
    searchParams.set("page", String(pageNum));
  }

  const query = searchParams.toString();
  return query ? `/blog?${query}` : "/blog";
}
