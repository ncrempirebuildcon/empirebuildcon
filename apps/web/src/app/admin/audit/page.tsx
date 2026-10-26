/**
 * /admin/audit: the audit log (board NoirCmsAudit). Needs `audit.read` (super-admin and admin);
 * the API checks it again. Read-only: the log can't be edited or deleted (INVARIANT in the API).
 */
import type { Metadata } from "next";
import { Suspense } from "react";
import { Alert } from "@empire/ui";
import { requireSessionUser } from "@/lib/session";
import { LoadingPanel } from "@/components/admin/states";
import { AdminShell } from "../AdminShell";
import { AuditScreen } from "./AuditScreen";

export const metadata: Metadata = { title: "Audit log" };
export const dynamic = "force-dynamic";

export default async function AuditPage() {
  const me = await requireSessionUser();
  const allowed = (me.permissions ?? []).includes("audit.read");
  return (
    <AdminShell me={me} section="audit" heading="Audit log">
      {allowed ? (
        // WHY Suspense: the filters live in the address (useSearchParams).
        <Suspense fallback={<LoadingPanel label="Loading the audit log…" rows={8} />}>
          <AuditScreen />
        </Suspense>
      ) : (
        <Alert tone="info">
          Your role can&apos;t read the audit log. Ask an admin if you need an entry checked.
        </Alert>
      )}
    </AdminShell>
  );
}
