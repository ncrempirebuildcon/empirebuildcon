/**
 * Visible ribbon shown in development and staging when sample data is displayed (S7).
 *
 * Implements ARCHITECTURE §15, D-038 & D-039:
 *   - Never rendered in production (checks APP_ENV === "production", S7).
 *   - Only displayed in development and staging when the page shows sample items (S7).
 *   - Matches NoirHome.dc.html top ribbon:
 *     "Sample data · project names, prices, RERA numbers and images are placeholders for review"
 */

export function SampleDataRibbon({ hasSampleData = false }: { hasSampleData?: boolean }) {
  // S7: Use APP_ENV only so staging (which runs next start with NODE_ENV=production) can show sample data
  const isProduction = process.env.APP_ENV === "production";
  if (isProduction || !hasSampleData) {
    return null;
  }

  return (
    <div
      role="status"
      aria-label="Sample data notice"
      className="border-b border-noir-700 bg-noir-800 px-4 py-1.5 text-center text-xs text-sand-400"
      data-testid="sample-data-ribbon"
    >
      Sample data · project names, prices, RERA numbers and images are placeholders for review
    </div>
  );
}

export default SampleDataRibbon;
