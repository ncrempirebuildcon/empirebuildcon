"use client";
/**
 * Public website header and mobile drawer navigation.
 *
 * Implements DESIGN_SYSTEM & D-038:
 *   - Skip link to main content (`#main-content`).
 *   - Logo from brand tokens (horizontal logo on desktop, mark on mobile).
 *   - Navigation driven by GET /public/site (pages with `show_in_nav`, in order, plus Projects).
 *   - Direct call/enquire CTA.
 *   - Mobile menu with real <button>, `aria-expanded`, focus trap, and Escape key handling.
 */
import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { buildTelLink, filterPlaceholders } from "@/lib/public/format";
import type { PublicSite } from "@/lib/public/api";

export interface HeaderProps {
  site?: PublicSite;
  isProduction?: boolean;
}

export function Header({ site, isProduction }: HeaderProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const pathname = usePathname();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);

  const company = site?.company;
  const phones = filterPlaceholders(company?.phones ?? [], isProduction);
  const primaryPhone = phones[0];
  const telHref = buildTelLink(primaryPhone, isProduction);

  // Nav items from site settings
  const customNav = site?.nav ?? [];

  // Close drawer on path change (React 19 state-during-render pattern)
  const [prevPathname, setPrevPathname] = useState(pathname);
  if (prevPathname !== pathname) {
    setPrevPathname(pathname);
    setMobileMenuOpen(false);
  }

  // Handle focus trap and Escape key for mobile menu
  useEffect(() => {
    if (!mobileMenuOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMobileMenuOpen(false);
        triggerRef.current?.focus();
        return;
      }

      if (e.key === "Tab" && drawerRef.current) {
        const focusables = drawerRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (focusables.length === 0) return;

        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (!first || !last) return;

        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    // Focus first element in drawer
    const timer = setTimeout(() => {
      if (drawerRef.current) {
        const first = drawerRef.current.querySelector<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        first?.focus();
      }
    }, 50);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      clearTimeout(timer);
    };
  }, [mobileMenuOpen]);

  return (
    <>
      {/* The skip link is the first thing on the page: (site)/layout.tsx (task 5.7). */}
      <header
        role="banner"
        className="sticky top-0 z-30 border-b border-gold-500/35 bg-noir-900/95 backdrop-blur-md"
        data-testid="public-header"
      >
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3.5 md:px-8">
          {/* Logo */}
          <Link href="/" aria-label="Empire home" className="flex min-h-11 items-center">
            <Image
              src="/brand/logo-horizontal-noir.svg"
              alt="Empire — Delivering Happiness"
              width={160}
              height={42}
              priority
              unoptimized
              className="h-9 md:h-11 w-auto"
            />
          </Link>

          {/* Desktop Navigation */}
          <nav
            aria-label="Main"
            className="hidden lg:flex flex-1 items-center justify-center gap-7 text-[15px] font-semibold text-sand-100"
          >
            <Link
              href="/projects"
              className={`inline-flex min-h-11 items-center hover:text-gold-300 transition-colors ${
                pathname?.startsWith("/projects") ? "text-gold-300 font-bold" : ""
              }`}
            >
              Projects
            </Link>
            {customNav.map((item) => (
              <Link
                key={item.path}
                href={item.path}
                className={`inline-flex min-h-11 items-center hover:text-gold-300 transition-colors ${
                  pathname === item.path ? "text-gold-300 font-bold" : ""
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>

          {/* Right Action / CTA */}
          <div className="flex items-center gap-3.5">
            {telHref && (
              <a
                href={telHref}
                className="hidden xl:inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-sand-100 hover:text-gold-300"
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="#E2B65A"
                  strokeWidth="1.7"
                  aria-hidden="true"
                >
                  <path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z" />
                </svg>
                {primaryPhone}
              </a>
            )}

            <Link
              href="/contact#visit"
              className="hidden sm:inline-flex min-h-[44px] items-center rounded-full bg-gold-500 px-5 text-sm font-extrabold text-noir-900 transition-colors hover:bg-gold-400"
            >
              Book a site visit
            </Link>

            {/* Mobile menu toggle button */}
            <button
              ref={triggerRef}
              type="button"
              aria-label="Open menu"
              aria-expanded={mobileMenuOpen}
              aria-controls="mobile-menu-drawer"
              onClick={() => setMobileMenuOpen((open) => !open)}
              className="lg:hidden flex h-11 w-11 items-center justify-center rounded-xl border border-noir-700 bg-noir-800 text-gold-400 hover:bg-noir-700"
              data-testid="mobile-menu-button"
            >
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                aria-hidden="true"
              >
                <path d="M4 7h16M4 12h16M4 17h16" />
              </svg>
            </button>
          </div>
        </div>
      </header>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div
          role="dialog"
          id="mobile-menu-drawer"
          aria-modal="true"
          aria-label="Mobile navigation menu"
          ref={drawerRef}
          className="fixed inset-0 z-50 flex flex-col bg-noir-900/98 backdrop-blur-xl lg:hidden"
          data-testid="mobile-menu-drawer"
        >
          {/* Drawer Header with Close Button */}
          <div className="flex items-center justify-between border-b border-gold-500/35 px-4 py-3.5">
            <Link
              href="/"
              onClick={() => setMobileMenuOpen(false)}
              aria-label="Empire home"
              className="flex min-h-11 items-center"
            >
              <Image
                src="/brand/logo-horizontal-noir.svg"
                alt="Empire — Delivering Happiness"
                width={140}
                height={36}
                unoptimized
                className="h-8 w-auto"
              />
            </Link>
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => {
                setMobileMenuOpen(false);
                triggerRef.current?.focus();
              }}
              className="flex h-11 w-11 items-center justify-center rounded-full border border-noir-700 bg-noir-800 text-sand-300 hover:text-gold-300"
              data-testid="mobile-menu-close"
            >
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                aria-hidden="true"
              >
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Drawer Navigation Links */}
          <nav
            aria-label="Mobile main"
            className="flex flex-1 flex-col gap-2 overflow-y-auto px-6 py-8"
          >
            <Link
              href="/projects"
              onClick={() => setMobileMenuOpen(false)}
              className="flex min-h-[44px] items-center text-lg font-semibold text-sand-100 hover:text-gold-300"
            >
              Projects
            </Link>
            {customNav.map((item) => (
              <Link
                key={item.path}
                href={item.path}
                onClick={() => setMobileMenuOpen(false)}
                className="flex min-h-[44px] items-center text-lg font-semibold text-sand-100 hover:text-gold-300"
              >
                {item.label}
              </Link>
            ))}

            <div className="my-4 border-t border-noir-800" />

            <Link
              href="/contact#visit"
              onClick={() => setMobileMenuOpen(false)}
              className="flex min-h-[48px] items-center justify-center rounded-full bg-gold-500 text-base font-extrabold text-noir-900 hover:bg-gold-400"
            >
              Book a site visit
            </Link>

            {telHref && (
              <a
                href={telHref}
                className="flex min-h-[44px] items-center justify-center gap-2 text-sm font-semibold text-sand-200 hover:text-gold-300"
              >
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="#E2B65A"
                  strokeWidth="1.7"
                  aria-hidden="true"
                >
                  <path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z" />
                </svg>
                {primaryPhone}
              </a>
            )}
          </nav>
        </div>
      )}
    </>
  );
}

export default Header;
