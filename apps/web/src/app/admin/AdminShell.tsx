"use client";
/**
 * CMS shell (design canvas "Black & gold — CMS" boards): sidebar, top bar, signed-in user,
 * and sign-out. The real screens arrive in Phase 4; until then the menu items are labelled.
 *
 * The menu only shows items the user's role can use (ARCHITECTURE.md §11). This is a convenience:
 * SECURITY: the API checks permissions on every call; hiding an item is never the protection.
 */
import Image from "next/image";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Alert, Button, Chip } from "@empire/ui";
import { api, type SessionUser } from "@/lib/api";

const ROLE_LABELS: Record<string, string> = {
  super_admin: "Super-admin",
  admin: "Admin",
  sales: "Sales",
  marketing: "Marketing",
  content_editor: "Content editor",
};

// Menu items from the CMS boards with the permission each one needs (ARCHITECTURE.md §11).
const MENU: Array<{ label: string; permission: string }> = [
  { label: "Dashboard", permission: "dashboard.view" },
  { label: "Leads", permission: "leads.read" },
  { label: "Site visits", permission: "site_visits.manage" },
  { label: "Projects", permission: "projects.read" },
  { label: "Media", permission: "media.upload" },
  { label: "Pages", permission: "content.read" },
  { label: "Offers & blog", permission: "offers.manage" },
  { label: "Users & roles", permission: "users.manage" },
  { label: "Settings", permission: "settings.read" },
  { label: "Audit log", permission: "audit.read" },
];

export function AdminShell({ me }: { me: SessionUser }) {
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const permissions = new Set(me.permissions ?? []);
  const visible = MENU.filter((item) => permissions.has(item.permission));
  const roleLabel = ROLE_LABELS[me.role] ?? me.role;

  useEffect(() => {
    // WHY: writes need the CSRF token bound to this session (SECURITY.md §3); keep it in memory only.
    api.setCsrfToken(me.csrf_token ?? null);
    return () => api.setCsrfToken(null);
  }, [me.csrf_token]);

  async function signOut() {
    setSigningOut(true);
    setError(null);
    try {
      const { response } = await api.POST("/api/v1/auth/logout");
      // 401 means the session had already ended: the result is the same, so carry on.
      if (!response.ok && response.status !== 401) throw new Error(String(response.status));
      router.replace("/admin/login");
    } catch {
      setSigningOut(false);
      setError("Couldn't sign you out. Check your connection and try again.");
    }
  }

  return (
    <div className="flex min-h-dvh flex-wrap">
      <aside
        aria-label="CMS navigation"
        className="flex w-full flex-col gap-5 border-b border-line bg-noir-950 px-3.5 py-5 md:w-62 md:border-r md:border-b-0"
      >
        <div className="flex items-center gap-2.5 px-2">
          <Image src="/brand/logo-mark-noir.svg" alt="" width={34} height={34} unoptimized />
          <div>
            <p className="font-display text-base font-semibold tracking-[0.2em] text-gold-400">
              EMPIRE
            </p>
            <p className="text-xs text-muted">CMS</p>
          </div>
        </div>
        <nav aria-label="Sections">
          <ul className="flex flex-col gap-1">
            {visible.map((item, index) => (
              <li key={item.label}>
                {index === 0 ? (
                  <span
                    aria-current="page"
                    className="flex min-h-11 items-center rounded-tile bg-gold-tint px-3 text-small font-semibold text-gold-300 shadow-[inset_3px_0_0_var(--color-gold-500)]"
                  >
                    {item.label}
                  </span>
                ) : (
                  <span className="flex min-h-11 items-center justify-between gap-2 rounded-tile px-3 text-small font-semibold text-body">
                    {item.label}
                    <span className="text-xs font-normal text-muted">Phase 4</span>
                  </span>
                )}
              </li>
            ))}
          </ul>
        </nav>
      </aside>

      <div className="flex min-w-0 flex-[999_1_560px] flex-col">
        <header className="flex min-h-16 flex-wrap items-center justify-between gap-3 border-b border-line px-7 py-3">
          <h1 className="text-[26px] font-bold">Dashboard</h1>
          <div className="flex items-center gap-3">
            <span className="text-small text-body">
              Signed in as <strong className="text-ivory">{me.name}</strong>
            </span>
            <Chip variant="draft">{roleLabel}</Chip>
            <Button variant="secondary" loading={signingOut} onClick={signOut}>
              Sign out
            </Button>
          </div>
        </header>
        <main className="flex flex-col gap-5 p-7">
          {error ? <Alert tone="error">{error}</Alert> : null}
          <section className="rounded-card border border-line bg-noir-800 p-6">
            <h2 className="mb-2 text-xl font-bold">Welcome, {me.name}</h2>
            <p className="max-w-[60ch]">
              You are signed in to the Empire CMS as{" "}
              <strong className="text-ivory">{roleLabel}</strong> ({me.email}). The CMS screens —
              leads, projects, media, pages and settings — arrive in Phase 4. This page proves that
              sign-in, roles and sign-out work end to end.
            </p>
          </section>
          <section className="rounded-card border border-line bg-noir-800 p-6">
            <h2 className="mb-3 text-base font-bold">Your permissions</h2>
            <ul className="flex flex-wrap gap-2" aria-label="Permissions">
              {[...permissions].sort().map((p) => (
                <li key={p}>
                  <code className="rounded-tag bg-noir-700 px-2 py-1 text-xs text-body">{p}</code>
                </li>
              ))}
            </ul>
          </section>
        </main>
      </div>
    </div>
  );
}
