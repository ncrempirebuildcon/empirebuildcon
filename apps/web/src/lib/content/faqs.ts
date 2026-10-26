/**
 * One FAQ group (the site-wide FAQs, or one project's) loaded in full, and the order a reorder
 * sends.
 *
 * WHY every page: the API lists at most 100 rows per request, but a reorder must name every FAQ
 * of the group exactly once (`PUT /admin/faqs/order`, 422 "Send every FAQ of this list…";
 * review L10). The API takes up to 500 ids in one reorder, so at most 5 pages are read.
 */
import { api, call, type Schema } from "@/lib/api";

export type Faq = Schema<"Faq">;

const PER_PAGE = 100;
/** 5 pages of 100: the most ids one reorder takes (ReorderRequest, 500). */
const MAX_PAGES = 5;

/** Every FAQ of the group, in the API's order (site-wide when `projectId` is null). */
export async function loadFaqGroup(projectId: string | null): Promise<Faq[]> {
  const items: Faq[] = [];
  for (let page = 1; page <= MAX_PAGES; page += 1) {
    const result = await call(
      api.GET("/api/v1/admin/faqs", {
        params: {
          query: projectId
            ? { project_id: projectId, page, per_page: PER_PAGE }
            : { site_wide: true, page, per_page: PER_PAGE },
        },
      }),
    );
    items.push(...result.items);
    if (page >= result.meta.pages) break;
  }
  return items;
}

/**
 * The full order to send: the order the user chose, minus FAQs someone else deleted since the
 * list loaded, then any FAQs someone else added (they were added at the end of the group anyway).
 */
export function fullGroupOrder(wanted: readonly string[], current: readonly string[]): string[] {
  const stillThere = new Set(current);
  const ordered = wanted.filter((id) => stillThere.has(id));
  const placed = new Set(ordered);
  return [...ordered, ...current.filter((id) => !placed.has(id))];
}

/** Reorders a whole group: reads it again first, so the request always names all of it. */
export async function reorderFaqGroup(
  projectId: string | null,
  wanted: readonly string[],
): Promise<Faq[]> {
  const current = await loadFaqGroup(projectId);
  const ids = fullGroupOrder(
    wanted,
    current.map((faq) => faq.id),
  );
  return call(api.PUT("/api/v1/admin/faqs/order", { body: { ids } }));
}
