/**
 * Visible ribbon shown in development and staging when sample data is displayed.
 *
 * Implements ARCHITECTURE §15 & D-038:
 *   - Never rendered in production.
 *   - Matches NoirHome.dc.html top ribbon:
 *     "Sample data · project names, prices, RERA numbers and images are placeholders for review"
 */

export function SampleDataRibbon() {
  const isProd = process.env.NODE_ENV === "production" || process.env.APP_ENV === "production";
  if (isProd) {
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
