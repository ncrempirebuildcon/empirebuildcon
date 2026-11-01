/**
 * 404 Page Not Found: Black & gold on-brand page (matches design board Noir404).
 *
 * Implements:
 *   - On-brand display heading, metallic 404 gradient, star-rule divider.
 *   - Quick navigation links: Projects, Properties, Contact, Home.
 *   - `noindex` metadata to prevent indexing broken links.
 */
import Link from "next/link";
import type { Metadata } from "next";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Page not found",
  robots: { index: false, follow: false },
};

export default function NotFound() {
  return (
    <main className="grid min-h-[70vh] place-items-center px-4 py-16">
      <div className="flex max-w-lg flex-col items-center gap-5 text-center">
        <p className="font-display text-xs font-semibold tracking-[0.28em] text-gold-400">
          PAGE NOT FOUND
        </p>

        <p
          className="font-display text-[clamp(72px,16vw,130px)] leading-none font-semibold text-metallic select-none"
          aria-hidden="true"
        >
          404
        </p>

        <div className="star-rule w-56 text-xs text-gold-500" aria-hidden="true">
          ✦
        </div>

        <h1 className="font-display text-2xl md:text-3xl font-semibold text-sand-100">
          This page has moved or doesn&apos;t exist
        </h1>

        <p className="text-sand-300 text-sm md:text-base max-w-md">
          The link may be old, or the project page may have a new address. Start from one of these
          pages.
        </p>

        <nav aria-label="Quick links" className="flex flex-wrap justify-center gap-2.5 pt-2">
          <Link
            href="/projects"
            className="rounded-full border border-gold-500 px-5 py-2 text-sm font-bold text-gold-300 hover:bg-gold-500/10"
          >
            Projects
          </Link>
          <Link
            href="/properties"
            className="rounded-full border border-gold-500 px-5 py-2 text-sm font-bold text-gold-300 hover:bg-gold-500/10"
          >
            Properties
          </Link>
          <Link
            href="/contact"
            className="rounded-full border border-gold-500 px-5 py-2 text-sm font-bold text-gold-300 hover:bg-gold-500/10"
          >
            Contact
          </Link>
          <Link
            href="/"
            className="rounded-full bg-gold-500 px-5 py-2 text-sm font-extrabold text-noir-900 hover:bg-gold-400"
          >
            Home
          </Link>
        </nav>
      </div>
    </main>
  );
}
