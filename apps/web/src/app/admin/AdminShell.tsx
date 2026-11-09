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
 *
 * The shell also loads the dashboard once per page (`GET /admin/dashboard`): the Leads item shows
 * the unread count from it as a badge, and the dashboard screen reads the same answer, so the
 * home page doesn't ask twice (`useAdminSession().dashboard`).
 */
import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { Alert, Button, Chip, ConfirmDialog } from "@empire/ui";
import { api, call, setCsrfToken, type SessionUser } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/labels";
import { unreadLeadCount } from "@/lib/leads/dashboard";
import {
  ACCOUNT_PATH,
  AUDIT_PATH,
  CATALOGUE_PATH,
  CONTENT_SECTIONS,
  LEADS_PATH,
  MEDIA_PATH,
  PAGES_PATH,
  PROJECTS_PATH,
  SETTINGS_PATH,
  SIGN_IN_PATH,
  SITE_VISITS_PATH,
  USERS_PATH,
  UTM_REPORT_PATH,
} from "@/lib/routes";
import { useLoad } from "@/components/admin/useLoad";
import { AdminSessionContext, type AdminSession, type DashboardState } from "./session-context";
import { NavIcon, type NavIconName } from "./NavIcon";

export type AdminSection =
  | "dashboard"
  | "leads"
  | "site_visits"
  | "reports"
  | "projects"
  | "catalogue"
  | "media"
  | "pages"
  | "content"
  | "users"
  | "settings"
  | "audit"
  | "account";

interface MenuItem {
  label: string;
  /** The permission the item needs; `anyOf` items need at least one of several instead. */
  permission: string;
  anyOf?: readonly string[];
  icon: NavIconName;
  href: string;
  section: AdminSection;
  /** Draw a divider above this item (board: before "Users & roles"). */
  divider?: boolean;
  /** Show the unread-leads badge from the dashboard counts. */
  badge?: "unread_leads";
}

// Menu items from the CMS boards with the permission each one needs (ARCHITECTURE.md §11).
const MENU: MenuItem[] = [
  {
    label: "Dashboard",
    permission: "dashboard.view",
    icon: "dashboard",
    href: "/admin",
    section: "dashboard",
  },
  {
    label: "Leads",
    permission: "leads.read",
    icon: "leads",
    href: LEADS_PATH,
    section: "leads",
    badge: "unread_leads",
  },
  {
    label: "Site visits",
    permission: "site_visits.manage",
    icon: "visits",
    href: SITE_VISITS_PATH,
    section: "site_visits",
  },
  {
    label: "Reports",
    permission: "leads.report",
    icon: "reports",
    href: UTM_REPORT_PATH,
    section: "reports",
  },
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
  {
    label: "Pages",
    permission: "content.read",
    icon: "pages",
    href: PAGES_PATH,
    section: "pages",
  },
  {
    // WHY anyOf: offers, posts/FAQs/testimonials and redirects need different permissions
    // (offers.manage, content.read, seo.manage); a content editor has no offers.manage but still
    // needs the blog. The link opens the first section the role can use (see `hrefFor`).
    label: "Offers & blog",
    permission: "offers.manage",
    anyOf: [...new Set(CONTENT_SECTIONS.map((section) => section.permission))],
    icon: "offers",
    href: CONTENT_SECTIONS[0].href,
    section: "content",
  },
  {
    label: "Users & roles",
    permission: "users.manage",
    icon: "users",
    href: USERS_PATH,
    section: "users",
    divider: true,
  },
  {
    label: "Settings",
    permission: "settings.read",
    icon: "settings",
    href: SETTINGS_PATH,
    section: "settings",
  },
  {
    label: "Audit log",
    permission: "audit.read",
    icon: "audit",
    href: AUDIT_PATH,
    section: "audit",
  },
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

  const permissions = useMemo(() => new Set(me.permissions ?? []), [me]);
  const hasDashboard = permissions.has("dashboard.view");
  const load = useLoad(`dashboard:${me.id}`, () =>
    hasDashboard ? call(api.GET("/api/v1/admin/dashboard")) : Promise.resolve(undefined),
  );
  const { data: dashboardData, error: dashboardError, loading: dashboardLoading } = load;
  const { reload: reloadDashboard, refresh: refreshDashboard } = load;
  const dashboard = useMemo<DashboardState | null>(
    () =>
      hasDashboard
        ? {
            data: dashboardData,
            error: dashboardError,
            loading: dashboardLoading,
            reload: reloadDashboard,
            refresh: async () => {
              await refreshDashboard();
            },
          }
        : null,
    [
      hasDashboard,
      dashboardData,
      dashboardError,
      dashboardLoading,
      reloadDashboard,
      refreshDashboard,
    ],
  );

  const session = useMemo<AdminSession>(
    () => ({
      me,
      can: (p) => permissions.has(p),
      setHeading: setTitle,
      setUnsaved,
      dashboard,
    }),
    [me, permissions, dashboard],
  );
  const visible = MENU.filter((item) =>
    item.anyOf ? item.anyOf.some((p) => session.can(p)) : session.can(item.permission),
  ).map((item) =>
    item.section === "content"
      ? {
          ...item,
          href: CONTENT_SECTIONS.find((entry) => session.can(entry.permission))?.href ?? item.href,
        }
      : item,
  );
  const unread = dashboard?.data ? unreadLeadCount(dashboard.data) : null;

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
              <Image src="/brand/logo-mark-noir.webp" alt="" width={57} height={34} unoptimized />
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
                    <MenuEntry
                      item={item}
                      current={item.section === section}
                      badge={item.badge === "unread_leads" ? unread : null}
                    />
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
              {/* Every role has an account page (password, two-factor), so no permission check. */}
              <Link
                href={ACCOUNT_PATH}
                aria-current={section === "account" ? "page" : undefined}
                className="inline-flex min-h-11 items-center px-1 text-small font-bold"
              >
                My account
              </Link>
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

function MenuEntry({
  item,
  current,
  badge,
}: {
  item: MenuItem;
  current: boolean;
  /** A count to show after the label (unread leads); nothing when null or zero. */
  badge: number | null;
}) {
  const base = "flex min-h-11 items-center gap-2.5 rounded-tile px-3 text-small font-semibold";
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
      {badge ? (
        // WHY the words in the link: "Leads 12 unread" is the link's name for screen readers,
        // and the visible number starts with the visible label (WCAG 2.5.3 Label in Name).
        <span className="ml-auto rounded-pill bg-gold-500 px-2 text-xs font-extrabold text-noir-900 tabular-nums">
          {badge > 99 ? "99+" : badge}
          <span className="sr-only"> unread</span>
        </span>
      ) : null}
    </Link>
  );
}
