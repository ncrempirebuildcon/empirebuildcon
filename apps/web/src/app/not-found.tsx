/**
 * 404 page in Black & gold (design canvas board "Noir404").
 * TODO(phase-5): add site search and quick links (Projects, Properties, Contact) once those pages exist;
 * linking to pages that don't exist yet would send visitors to another 404.
 */
import Link from "next/link";
import type { Metadata } from "next";
import { buttonClasses } from "@empire/ui";

export const metadata: Metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <main className="grid min-h-dvh place-items-center px-4 py-12">
      <div className="flex max-w-lg flex-col items-center gap-5 text-center">
        <p
          className="font-display text-[clamp(72px,16vw,128px)] leading-none font-semibold text-metallic"
          aria-hidden="true"
        >
          404
        </p>
        <div className="star-rule w-56 text-xs" aria-hidden="true">
          ✦
        </div>
        <h1 className="font-display text-h3 font-semibold">
          This page has moved or doesn&apos;t exist
        </h1>
        <p className="text-body">Check the address, or start again from the home page.</p>
        <Link href="/" className={buttonClasses("primary")}>
          Go to the home page
        </Link>
      </div>
    </main>
  );
}
