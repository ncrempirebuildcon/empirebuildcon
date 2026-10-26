"use client";
/**
 * My account: who you are signed in as, your password, and two-factor sign-in (admins and
 * super-admins). One unsaved-changes guard for the screen (useUnsavedChanges explains why).
 */
import { useCallback } from "react";
import { ROLE_LABELS } from "@/lib/labels";
import { Panel } from "@/components/admin/states";
import { useDirtyParts, useUnsavedChanges } from "@/components/admin/useUnsavedChanges";
import { useAdminSession } from "../session-context";
import { ChangePassword } from "./ChangePassword";
import { TwoFactorPanel } from "./TwoFactorPanel";

export function AccountScreen() {
  const { me } = useAdminSession();
  const parts = useDirtyParts();
  const { report } = parts;
  const onPasswordDirty = useCallback((dirty: boolean) => report("password", dirty), [report]);
  const onTwoFactorDirty = useCallback((dirty: boolean) => report("two-factor", dirty), [report]);
  const { dialog } = useUnsavedChanges(parts.dirty);

  return (
    <>
      <Panel
        id="me"
        title="Your account"
        description="Ask the super-admin to change your name, email or role."
      >
        <dl className="grid gap-x-6 gap-y-2 text-small sm:grid-cols-[auto_1fr]">
          <dt className="text-muted">Name</dt>
          <dd className="font-semibold text-ivory">{me.name}</dd>
          <dt className="text-muted">Work email</dt>
          <dd className="[overflow-wrap:anywhere] text-ivory">{me.email}</dd>
          <dt className="text-muted">Role</dt>
          <dd className="text-ivory">{ROLE_LABELS[me.role] ?? me.role}</dd>
        </dl>
      </Panel>
      <ChangePassword onDirtyChange={onPasswordDirty} />
      <TwoFactorPanel onDirtyChange={onTwoFactorDirty} />
      {dialog}
    </>
  );
}
