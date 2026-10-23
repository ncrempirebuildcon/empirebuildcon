"use client";
/**
 * CMS shell (design boards NoirCmsDashboard and NoirCmsProject): 248 px sidebar with the menu,
 * a 64 px top bar with the page heading, the signed-in user and sign-out, and the page content.
 *
 * Every CMS page renders this around its screen after the server session check
 * (lib/session.ts `requireSessionUser`). Screens read the user and permissions through
 * `useAdminSession()` and can replace the heading with `useAdminHeading()`.
 *
 * The menu only shows items the user's role can use (ARCHITECTURE.md §11). This is a convenience:
 * SECURITY: the API checks permissions on every call; hiding an item is never the protection.
 */
import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { Alert, Button, Chip, ConfirmDialog } from "@empire/ui";
import { api, setCsrfToken, type SessionUser } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/labels";
import { CATALOGUE_PATH, MEDIA_PATH, PROJECTS_PATH, SIGN_IN_PATH } from "@/lib/routes";
import { AdminSessionContext, type AdminSession } from "./session-context";
import { NavIcon, type NavIconName } from "./NavIcon";

export type AdminSection = "dashboard" | "projects" | "catalogue" | "media";

interface MenuItem {
  label: string;
  permission: string;
  icon: NavIconName;
  /** Built screens link here; the others are labelled with the part that brings them. */
  href?: string;
  section?: AdminSection;
  /** Draw a divider above this item (board: before "Users & roles"). */
  divider?: boolean;
}

// Menu items from the CMS boards with the permission each one needs (ARCHITECTURE.md §11).
// TODO(phase-4): link Leads, Site visits, Pages, Offers & blog, Users, Settings and Audit log as
// their screens arrive in the later parts of Phase 4.
const MENU: MenuItem[] = [
  {
    label: "Dashboard",
    permission: "dashboard.view",
    icon: "dashboard",
    href: "/admin",
    section: "dashboard",
  },
  { label: "Leads", permission: "leads.read", icon: "leads" },
  { label: "Site visits", permission: "site_visits.manage", icon: "visits" },
  {
    label: "Projects",
    permission: "projects.read",
    icon: "projects",
    href: PROJECTS_PATH,
    section: "projects",
  },
  {
    label: "Catalogue",
    permission: "projects.read",
    icon: "catalogue",
    href: CATALOGUE_PATH,
    section: "catalogue",
  },
  {
    label: "Media",
    permission: "media.upload",
    icon: "media",
    href: MEDIA_PATH,
    section: "media",
  },
  { label: "Pages", permission: "content.read", icon: "pages" },
  { label: "Offers & blog", permission: "offers.manage", icon: "offers" },
  { label: "Users & roles", permission: "users.manage", icon: "users", divider: true },
  { label: "Settings", permission: "settings.read", icon: "settings" },
  { label: "Audit log", permission: "audit.read", icon: "audit" },
];

export interface AdminShellProps {
  me: SessionUser;
  /** Which menu item is current. */
  section: AdminSection;
  /** The page heading (h1) in the top bar; screens may replace it with `useAdminHeading`. */
  heading: string;
  /** Optional parent link shown before the heading, e.g. Projects / Aurum Heights. */
  breadcrumb?: { href: string; label: string };
  children: ReactNode;
}

export function AdminShell({ me, section, heading, breadcrumb, children }: AdminShellProps) {
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState(heading);
  const [menuOpen, setMenuOpen] = useState(false);
  // True while the screen has unsaved changes (useUnsavedChanges reports it); Sign out asks first.
  const [unsaved, setUnsaved] = useState(false);
  const [confirmSignOut, setConfirmSignOut] = useState(false);
  const roleLabel = ROLE_LABELS[me.role] ?? me.role;

  const session = useMemo<AdminSession>(() => {
    const permissions = new Set(me.permissions ?? []);
    return { me, can: (p) => permissions.has(p), setHeading: setTitle, setUnsaved };
  }, [me]);
  const visible = MENU.filter((item) => session.can(item.permission));

  useEffect(() => {
    // WHY: writes need the CSRF token bound to this session (SECURITY.md §3); keep it in memory only.
    setCsrfToken(me.csrf_token ?? null);
    return () => setCsrfToken(null);
  }, [me.csrf_token]);

  const signOut = useCallback(async () => {
    setSigningOut(true);
    setError(null);
    try {
      const { response } = await api.POST("/api/v1/auth/logout");
      // 401 means the session had already ended: the result is the same, so carry on.
      if (!response.ok && response.status !== 401) throw new Error(String(response.status));
      router.replace(SIGN_IN_PATH);
    } catch {
      setSigningOut(false);
      setError("Couldn't sign you out. Check your connection and try again.");
    }
  }, [router]);

  return (
    <AdminSessionContext.Provider value={session}>
      <a
        href="#main"
        className="sr-only z-10 rounded-tile bg-gold-500 px-4 py-3 font-bold text-noir-900 focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>
      <div className="flex min-h-dvh flex-wrap">
        <aside
          aria-label="CMS navigation"
          className="flex w-full flex-col gap-5 border-b border-line bg-noir-950 px-3.5 py-5 md:w-62 md:border-r md:border-b-0"
        >
          <div className="flex items-center justify-between gap-3">
            {/* WHY no aria-label: the visible words are the link's name (WCAG 2.5.3 Label in Name). */}
            <Link href="/admin" className="flex items-center gap-2.5 px-2">
              <Image src="/brand/logo-mark-noir.svg" alt="" width={34} height={34} unoptimized />
              <span className="flex flex-col leading-tight">
                <span className="font-display text-base font-semibold tracking-[0.2em] text-gold-400">
                  EMPIRE
                </span>{" "}
                <span className="text-xs text-muted">CMS</span>
              </span>
            </Link>
            {/* WHY: on a phone the full menu would push every screen below the fold. */}
            <button
              type="button"
              aria-expanded={menuOpen}
              aria-controls="cms-menu"
              onClick={() => setMenuOpen((open) => !open)}
              className="min-h-11 rounded-pill border border-gold-500 px-4 text-small font-bold text-gold-300 md:hidden"
            >
              {menuOpen ? "Close menu" : "Menu"}
            </button>
          </div>
          <div
            id="cms-menu"
            className={`${menuOpen ? "flex" : "hidden"} flex-1 flex-col gap-5 md:flex`}
          >
            <nav aria-label="Sections">
              <ul className="flex flex-col gap-0.5">
                {visible.map((item) => (
                  <li key={item.label}>
                    {item.divider ? (
                      <span aria-hidden="true" className="my-2 block h-px bg-line" />
                    ) : null}
                    <MenuEntry item={item} current={item.section === section} />
                  </li>
                ))}
              </ul>
            </nav>
            <Link href="/" className="mt-auto px-3 text-small font-bold">
              View website <span aria-hidden="true">↗</span>
            </Link>
          </div>
        </aside>

        <div className="flex min-w-0 flex-[999_1_560px] flex-col">
          <header className="flex min-h-16 flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3 md:px-7">
            <div className="flex min-w-0 flex-wrap items-baseline gap-2.5">
              {breadcrumb ? (
                <>
                  <Link href={breadcrumb.href} className="text-small font-semibold">
                    {breadcrumb.label}
                  </Link>
                  <span aria-hidden="true" className="text-muted">
                    /
                  </span>
                </>
              ) : null}
              <h1 className="text-[26px] font-bold [overflow-wrap:anywhere]">{title}</h1>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-small text-body">
                Signed in as <strong className="text-ivory">{me.name}</strong>
              </span>
              <Chip variant="draft">{roleLabel}</Chip>
              <Button
                variant="secondary"
                loading={signingOut}
                onClick={() => (unsaved ? setConfirmSignOut(true) : void signOut())}
              >
                Sign out
              </Button>
            </div>
          </header>
          <main id="main" tabIndex={-1} className="flex flex-col gap-5 px-4 pt-5 pb-10 md:px-7">
            {error ? <Alert tone="error">{error}</Alert> : null}
            {children}
          </main>
        </div>
      </div>
      <ConfirmDialog
        open={confirmSignOut}
        title="Sign out without saving?"
        confirmLabel="Sign out without saving"
        cancelLabel="Stay signed in"
        tone="danger"
        busy={signingOut}
        onCancel={() => setConfirmSignOut(false)}
        onConfirm={() => void signOut()}
      >
        You have changes that are not saved yet. If you sign out now, they are lost.
      </ConfirmDialog>
    </AdminSessionContext.Provider>
  );
}

function MenuEntry({ item, current }: { item: MenuItem; current: boolean }) {
  const base = "flex min-h-11 items-center gap-2.5 rounded-tile px-3 text-small font-semibold";
  if (item.href) {
    return (
      <Link
        href={item.href}
        aria-current={current ? "page" : undefined}
        className={
          current
            ? `${base} bg-gold-tint text-gold-300 shadow-[inset_3px_0_0_var(--color-gold-500)]`
            : `${base} text-body hover:bg-noir-800 hover:text-gold-300`
        }
      >
        <NavIcon name={item.icon} />
        {item.label}
      </Link>
    );
  }
  return (
    <span className={`${base} justify-between text-body`}>
      <span className="flex items-center gap-2.5">
        <NavIcon name={item.icon} />
        {item.label}
      </span>
      <span className="text-xs font-normal text-muted">Soon</span>
    </span>
  );
}
