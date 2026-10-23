/**
 * /admin/leads: the lead inbox. Session checked on the server, leads loaded in the browser
 * (ARCHITECTURE.md §5: CMS pages are client-rendered and never cached; next.config.ts sends
 * no-store because they hold personal data). Needs `leads.read`; the API checks it again and
 * applies the object-level rule (SECURITY.md §1).
 */
import type { Metadata } from "next";
import { Suspense } from "react";
import { Alert } from "@empire/ui";
import { requireSessionUser } from "@/lib/session";
import { LoadingPanel } from "@/components/admin/states";
import { AdminShell } from "../AdminShell";
import { LeadsInbox } from "./LeadsInbox";

export const metadata: Metadata = { title: "Leads" };
export const dynamic = "force-dynamic";

export default async function LeadsPage() {
  const me = await requireSessionUser();
  const allowed = (me.permissions ?? []).includes("leads.read");
  return (
    <AdminShell me={me} section="leads" heading="Leads">
      {allowed ? (
        // WHY Suspense: the inbox reads its filters with useSearchParams().
        <Suspense fallback={<LoadingPanel label="Loading leads…" rows={6} />}>
          <LeadsInbox />
        </Suspense>
      ) : (
        <Alert tone="info">Your role can&apos;t open leads. Ask an admin if you need them.</Alert>
      )}
    </AdminShell>
  );
}
