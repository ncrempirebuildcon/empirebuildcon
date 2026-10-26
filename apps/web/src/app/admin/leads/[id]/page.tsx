/**
 * /admin/leads/[id]: one lead. Session checked on the server; the lead is loaded in the browser
 * (ARCHITECTURE.md §5). Needs `leads.read`; the API checks it again and answers 404 for a lead
 * this user may not see (SECURITY.md §1). The page is never cached (next.config.ts, no-store).
 */
import type { Metadata } from "next";
import { Alert } from "@empire/ui";
import { requireSessionUser } from "@/lib/session";
import { LEADS_PATH } from "@/lib/routes";
import { AdminShell } from "../../AdminShell";
import { LeadDetail } from "./LeadDetail";

// WHY a generic title: the browser tab and history must not carry the person's name.
export const metadata: Metadata = { title: "Lead" };
export const dynamic = "force-dynamic";

export default async function LeadPage({ params }: { params: Promise<{ id: string }> }) {
  const me = await requireSessionUser();
  const { id } = await params;
  const allowed = (me.permissions ?? []).includes("leads.read");
  return (
    <AdminShell
      me={me}
      section="leads"
      heading="Lead"
      breadcrumb={{ href: LEADS_PATH, label: "Leads" }}
    >
      {allowed ? (
        <LeadDetail id={id} />
      ) : (
        <Alert tone="info">Your role can&apos;t open leads. Ask an admin if you need them.</Alert>
      )}
    </AdminShell>
  );
}
