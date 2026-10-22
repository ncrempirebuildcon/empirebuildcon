/**
 * CMS home: checks the session on the server, then renders the client shell.
 * Signed out (or session expired/revoked) → /admin/login. API unreachable → error.tsx.
 */
import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { getSessionUser } from "@/lib/session";
import { AdminShell } from "./AdminShell";

export const metadata: Metadata = { title: "Dashboard" };
export const dynamic = "force-dynamic";

export default async function AdminHome() {
  const me = await getSessionUser();
  if (!me) redirect("/admin/login");
  return <AdminShell me={me} />;
}
