/**
 * Read time calculation for blog articles (Phase 5 Task 5.5b).
 *
 * Rules:
 *   - Word count of post body ÷ 200, rounded up, minimum 1.
 *   - Formatted as "N min read".
 *   - Empty or null body defaults to 1 min ("1 min read").
 */

export function calculateReadTimeMinutes(body: string | null | undefined): number {
  if (!body) return 1;
  const words = body.trim().split(/\s+/).filter(Boolean).length;
  if (words === 0) return 1;
  return Math.max(1, Math.ceil(words / 200));
}

export function formatReadTime(body: string | null | undefined): string {
  const minutes = calculateReadTimeMinutes(body);
  return `${minutes} min read`;
}
