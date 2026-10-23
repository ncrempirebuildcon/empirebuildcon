/**
 * /admin/reports/utm: leads by campaign tags, counts only. Session checked on the server; the
 * report is loaded in the browser (ARCHITECTURE.md §5). Needs `leads.report`; the API checks it
 * again.
 */
import type { Metadata } from "next";
import { Suspense } from "react";
import { Alert } from "@empire/ui";
import { requireSessionUser } from "@/lib/session";
import { LoadingPanel } from "@/components/admin/states";
import { AdminShell } from "../../AdminShell";
import { UtmReport } from "./UtmReport";

export const metadata: Metadata = { title: "UTM report" };
export const dynamic = "force-dynamic";

export default async function UtmReportPage() {
  const me = await requireSessionUser();
  const allowed = (me.permissions ?? []).includes("leads.report");
  return (
    <AdminShell me={me} section="reports" heading="UTM report">
      {allowed ? (
        // WHY Suspense: the report reads its dates with useSearchParams().
        <Suspense fallback={<LoadingPanel label="Loading the report…" rows={5} />}>
          <UtmReport />
        </Suspense>
      ) : (
        <Alert tone="info">Your role can&apos;t open reports. Ask an admin if you need them.</Alert>
      )}
    </AdminShell>
  );
}
