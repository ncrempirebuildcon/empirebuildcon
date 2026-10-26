/**
 * /admin/users: Users & roles (board NoirCmsUsers): invite staff, manage their accounts, and the
 * role matrix. Super-admin only (`users.manage`); the API checks it again on every call.
 */
import type { Metadata } from "next";
import { Suspense } from "react";
import { Alert } from "@empire/ui";
import { requireSessionUser } from "@/lib/session";
import { LoadingPanel } from "@/components/admin/states";
import { AdminShell } from "../AdminShell";
import { UsersScreen } from "./UsersScreen";

export const metadata: Metadata = { title: "Users & roles" };
export const dynamic = "force-dynamic";

export default async function UsersPage() {
  const me = await requireSessionUser();
  const allowed = (me.permissions ?? []).includes("users.manage");
  return (
    <AdminShell me={me} section="users" heading="Users & roles">
      {allowed ? (
        // WHY Suspense: the screen keeps its filters and the open user in the address.
        <Suspense fallback={<LoadingPanel label="Loading users…" rows={6} />}>
          <UsersScreen />
        </Suspense>
      ) : (
        <Alert tone="info">
          Only the super-admin can manage users and roles. Ask them if someone needs an account.
        </Alert>
      )}
    </AdminShell>
  );
}
