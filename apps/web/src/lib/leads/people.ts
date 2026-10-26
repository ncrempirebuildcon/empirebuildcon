/**
 * Staff names as the lead screens show them: initials for the owner badge on pipeline cards
 * ("Sales 1" → "S1", "Priya Singh" → "PS"), as on board NoirCmsLeads.
 */

/** Up to two initials from a name; digits are kept, so "Sales 2" reads "S2". */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const letters = words.slice(0, 2).map((word) => word.charAt(0).toUpperCase());
  return letters.join("") || "–";
}
