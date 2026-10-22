/**
 * CMS home: checks the session on the server, then renders the client shell and the dashboard.
 * Signed out (or session expired/revoked) → /admin/login. API unreachable → error.tsx.
 */
import type { Metadata } from "next";
import { requireSessionUser } from "@/lib/session";
import { AdminShell } from "./AdminShell";
import { DashboardHome } from "./DashboardHome";

export const metadata: Metadata = { title: "Dashboard" };
export const dynamic = "force-dynamic";

export default async function AdminHome() {
  const me = await requireSessionUser();
  return (
    <AdminShell me={me} section="dashboard" heading="Dashboard">
      <DashboardHome />
    </AdminShell>
  );
}
