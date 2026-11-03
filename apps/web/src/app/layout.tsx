/**
 * Root layout: fonts, global styles and site-wide metadata.
 *
 * Fonts are self-hosted from npm (@fontsource files), so pages make no requests to Google Fonts
 * (privacy, and a simpler Content-Security-Policy).
 *
 * PERF (task 5.7, D-049): the files go through next/font/local, which preloads them and gives
 * the fallback font the same size (no layout shift). Before, the headings waited for a CSS
 * file to discover the font, which made the project page's h1 the slow LCP element on phones.
 * Only the Latin subset is loaded; other characters fall back to the system font.
 */
import localFont from "next/font/local";
import { SITE_DESCRIPTION } from "@/lib/public/seo";
import "./globals.css";

import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

const display = localFont({
  src: [
    {
      path: "../../node_modules/@fontsource/cinzel/files/cinzel-latin-600-normal.woff2",
      weight: "600",
    },
    {
      path: "../../node_modules/@fontsource/cinzel/files/cinzel-latin-700-normal.woff2",
      weight: "700",
    },
  ],
  variable: "--font-cinzel",
  display: "swap",
  fallback: ["Georgia", "serif"],
});

// WHY: the Latin file has no ₹ (U+20B9); it is in the latin-ext file. This face holds only that
// character (unicode-range) and loads only when a page shows a price, so every price keeps the
// site's font. No fallback of its own: other characters fall through to Manrope.
const rupee = localFont({
  src: "../../node_modules/@fontsource-variable/manrope/files/manrope-latin-ext-wght-normal.woff2",
  weight: "200 800",
  variable: "--font-rupee",
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  fallback: [],
  declarations: [{ prop: "unicode-range", value: "U+20B9" }],
});

const sans = localFont({
  src: "../../node_modules/@fontsource-variable/manrope/files/manrope-latin-wght-normal.woff2",
  weight: "200 800",
  variable: "--font-manrope",
  display: "swap",
  fallback: ["Segoe UI", "system-ui", "sans-serif"],
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.SITE_URL ?? "http://localhost:3000"),
  title: { default: "Empire · Delivering Happiness", template: "%s · Empire" },
  description: SITE_DESCRIPTION,
  // TODO(phase-9): allow indexing at go-live (Phase 9 gate). Until then nothing is indexed.
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: "#0E0C0A",
  colorScheme: "dark",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${rupee.variable} ${sans.variable}`}>
      <body className="min-h-dvh bg-noir-900 font-sans text-body antialiased">{children}</body>
    </html>
  );
}
