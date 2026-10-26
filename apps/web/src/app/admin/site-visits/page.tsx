/**
 * /admin/site-visits: the site-visit calendar. Session checked on the server, visits loaded in
 * the browser (ARCHITECTURE.md §5). Needs `site_visits.manage`; the API checks it again.
 */
import type { Metadata } from "next";
import { Suspense } from "react";
import { Alert } from "@empire/ui";
import { requireSessionUser } from "@/lib/session";
import { LoadingPanel } from "@/components/admin/states";
import { AdminShell } from "../AdminShell";
import { VisitsCalendar } from "./VisitsCalendar";

export const metadata: Metadata = { title: "Site visits" };
export const dynamic = "force-dynamic";

export default async function SiteVisitsPage() {
  const me = await requireSessionUser();
  const allowed = (me.permissions ?? []).includes("site_visits.manage");
  return (
    <AdminShell me={me} section="site_visits" heading="Site visits">
      {allowed ? (
        // WHY Suspense: the calendar reads the view, date and filters with useSearchParams().
        <Suspense fallback={<LoadingPanel label="Loading site visits…" rows={5} />}>
          <VisitsCalendar />
        </Suspense>
      ) : (
        <Alert tone="info">
          Your role can&apos;t open the site-visit calendar. Ask an admin if you need it.
        </Alert>
      )}
    </AdminShell>
  );
}
