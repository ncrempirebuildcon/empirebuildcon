/**
 * The frame of the signed-out CMS pages (board NoirCmsLogin): the stacked logo, one gold-edged
 * card with an eyebrow and heading, and the "staff only" line under it. Used by sign-in, "forgot
 * password" and the setup and reset pages.
 *
 * SECURITY: these pages load nothing from other sites (the logo and fonts are ours), so a
 * setup or reset link in the address can't leak to a third party (SECURITY.md §1).
 */
import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";

export interface AuthCardProps {
  /** Small gold line above the heading, e.g. "EMPIRE CMS" or "STEP 2 OF 2". */
  eyebrow: string;
  /** The page's h1. */
  title: string;
  /** Optional sentence under the heading. */
  intro?: ReactNode;
  children: ReactNode;
}

export function AuthCard({ eyebrow, title, intro, children }: AuthCardProps) {
  return (
    <main className="grid min-h-dvh place-items-center px-4 py-10">
      <div className="flex w-full max-w-md flex-col items-center gap-6">
        <Image
          src="/brand/logo-stacked-noir.svg"
          alt="Empire — Delivering Happiness"
          width={180}
          height={140}
          priority
          unoptimized
          className="h-auto w-[180px]"
        />
        <section
          aria-labelledby="auth-title"
          className="flex w-full flex-col gap-5 rounded-card-lg border border-gold-line-strong bg-noir-800 p-6 sm:p-8"
        >
          <div className="flex flex-col gap-1">
            <p className="font-display text-xs font-semibold tracking-[0.28em] text-gold-400">
              {eyebrow}
            </p>
            <h1 id="auth-title" className="text-[26px] font-bold">
              {title}
            </h1>
            {intro ? <div className="text-small text-body">{intro}</div> : null}
          </div>
          {children}
        </section>
        <p className="text-center text-caption text-muted">
          Empire staff only · no public sign-up · accounts are created by the super-admin
        </p>
        <Link href="/" className="text-caption font-bold">
          Back to the website
        </Link>
      </div>
    </main>
  );
}
