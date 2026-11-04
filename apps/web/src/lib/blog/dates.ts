/**
 * Date formatting for blog posts and cards (Phase 5 Task 5.5b).
 *
 * Implements DESIGN_SYSTEM §3 & Task 5.5b:
 *   - Dates in Indian format: "12 Oct 2026", in Asia/Kolkata timezone.
 *   - Delegates to our tested `formatDate` helper in `src/lib/dates.ts`.
 */
import { formatDate } from "@/lib/dates";

export function formatBlogDate(isoDate: string | null | undefined): string {
  if (!isoDate) return "";
  return formatDate(isoDate);
}
