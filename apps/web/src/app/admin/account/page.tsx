/**
 * /admin/account ("My account", linked from the header): change your own password and, for
 * admins and super-admins, two-factor sign-in. Every signed-in role has it. Session checked on
 * the server; the screen works in the browser (ARCHITECTURE.md §5).
 */
import type { Metadata } from "next";
import { requireSessionUser } from "@/lib/session";
import { AdminShell } from "../AdminShell";
import { AccountScreen } from "./AccountScreen";

export const metadata: Metadata = { title: "My account" };
export const dynamic = "force-dynamic";

export default async function AccountPage() {
  const me = await requireSessionUser();
  return (
    <AdminShell me={me} section="account" heading="My account">
      <AccountScreen />
    </AdminShell>
  );
}
