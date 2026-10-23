"use client";
/**
 * Dashboard content until the counts arrive: a welcome, shortcuts to the screens that exist,
 * and the signed-in role's permissions.
 * TODO(phase-4): the "At a glance" counts, latest leads and site visits (part 3, board
 * NoirCmsDashboard).
 */
import Link from "next/link";
import { buttonClasses } from "@empire/ui";
import { CATALOGUE_PATH, MEDIA_PATH, PROJECTS_PATH } from "@/lib/routes";
import { ROLE_LABELS } from "@/lib/labels";
import { useAdminSession } from "./session-context";

export function DashboardHome() {
  const { me, can } = useAdminSession();
  const roleLabel = ROLE_LABELS[me.role] ?? me.role;
  const permissions = [...(me.permissions ?? [])].sort();

  return (
    <>
      <section className="rounded-card border border-line bg-noir-800 p-6">
        <h2 className="mb-2 text-xl font-bold">Welcome, {me.name}</h2>
        <p className="max-w-[60ch]">
          You are signed in to the Empire CMS as <strong className="text-ivory">{roleLabel}</strong>{" "}
          ({me.email}). Projects, their media and the catalogue of cities, localities and amenities
          are ready. Leads, pages and settings arrive in the next updates.
        </p>
        {can("projects.read") || can("media.upload") ? (
          <div className="mt-4 flex flex-wrap gap-3">
            {can("projects.read") ? (
              <>
                <Link href={PROJECTS_PATH} className={buttonClasses("primary")}>
                  Manage projects
                </Link>
                <Link href={CATALOGUE_PATH} className={buttonClasses("secondary")}>
                  Cities, localities and amenities
                </Link>
              </>
            ) : null}
            {can("media.upload") ? (
              <Link href={MEDIA_PATH} className={buttonClasses("secondary")}>
                Media library
              </Link>
            ) : null}
          </div>
        ) : null}
      </section>
      <section className="rounded-card border border-line bg-noir-800 p-6">
        <h2 className="mb-3 text-base font-bold">Your permissions</h2>
        <ul className="flex flex-wrap gap-2" aria-label="Permissions">
          {permissions.map((p) => (
            <li key={p}>
              <code className="rounded-tag bg-noir-700 px-2 py-1 text-xs text-body">{p}</code>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
