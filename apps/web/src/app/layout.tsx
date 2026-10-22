/**
 * Root layout: fonts, global styles and site-wide metadata.
 *
 * Fonts are self-hosted from npm (@fontsource), so pages make no requests to Google Fonts
 * (privacy, and a simpler Content-Security-Policy in Phase 5).
 */
import "@fontsource/cinzel/600.css";
import "@fontsource/cinzel/700.css";
import "@fontsource-variable/manrope";
import "./globals.css";

import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.SITE_URL ?? "http://localhost:3000"),
  title: { default: "Empire · Delivering Happiness", template: "%s · Empire" },
  description: "Empire — Delivering Happiness. Our new website is on its way.",
  // TODO(phase-9): allow indexing at go-live (Phase 9 gate). Until then nothing is indexed.
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: "#0E0C0A",
  colorScheme: "dark",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-dvh bg-noir-900 font-sans text-body antialiased">{children}</body>
    </html>
  );
}
