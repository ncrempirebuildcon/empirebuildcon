/**
 * Line icons for the CMS menu, copied from the CMS boards (24 px grid, 1.6 stroke, gold-400;
 * DESIGN_SYSTEM §6). Decorative: every menu item also has a text label.
 */
const PATHS = {
  dashboard: ["M3 3h7v7H3z", "M14 3h7v7h-7z", "M3 14h7v7H3z", "M14 14h7v7h-7z"],
  leads: ["M3 13l3-8h12l3 8v6H3z", "M3 13h5l1 3h6l1-3h5"],
  visits: ["M3 5h18v16H3z", "M3 10h18M8 3v4M16 3v4"],
  projects: ["M4 21V9h6v12M14 21V4h6v17M2 21h20"],
  catalogue: ["M4 5h16M4 12h16M4 19h10", "M18 17l2 2 3-4"],
  media: ["M3 4h18v16H3z", "M21 17l-6-6-9 9", "M9 8a2 2 0 1 0 0 4 2 2 0 0 0 0-4"],
  pages: ["M14 3H6v18h12V7z", "M14 3v4h4M9 13h6M9 17h6"],
  offers: ["M3 11v2a1 1 0 0 0 1 1h2l5 4V6L6 10H4a1 1 0 0 0-1 1z", "M15 9a4 4 0 0 1 0 6"],
  users: ["M9 5a3 3 0 1 0 0 6 3 3 0 0 0 0-6", "M3 20c0-3 3-5 6-5s6 2 6 5", "M16 15c3 0 5 1.5 5 4"],
  settings: [
    "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6",
    "M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1",
  ],
  audit: ["M12 3l7 3v5c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6l7-3z", "M9 11h6M9 15h4"],
} as const satisfies Record<string, readonly string[]>;

export type NavIconName = keyof typeof PATHS;

export function NavIcon({ name }: { name: NavIconName }) {
  return (
    <svg
      aria-hidden="true"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="shrink-0 text-gold-400"
    >
      {PATHS[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
