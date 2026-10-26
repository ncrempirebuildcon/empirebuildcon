"use client";
/**
 * Manage one staff account, beside the users table (board NoirCmsUsers' row actions): change
 * the role, unlock, send a reset link (or a new setup link if they never set a password: "Resend
 * invite"), sign out everywhere, reset two-factor (lost phone), deactivate or reactivate. Every action except unlock and
 * the links asks first (ConfirmDialog); the answer appears as a status message.
 *
 * SECURITY: the API is the gate (`users.manage`) and refuses demoting or deactivating the last
 * usable super-admin with a 409, whose sentence is shown as it comes. Your own account's role,
 * sessions and two-factor are changed under My account or by another super-admin, so those
 * actions are not offered here for yourself (a slip would lock you out mid-task).
 */
import { useState } from "react";
import { Alert, Button, ConfirmDialog, Select } from "@empire/ui";
import { api, call } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { ROLE_LABELS } from "@/lib/labels";
import { problemMessage } from "@/lib/problems";
import { ACCOUNT_STATUS, ROLE_ORDER, accountStatus, type RoleKey } from "@/lib/users";
import { useReportDirty } from "@/components/admin/useUnsavedChanges";
import { addedText, twoFactorText, type StaffUser } from "./userText";

interface Pending {
  title: string;
  body: string;
  confirmLabel: string;
  tone: "danger" | "default";
  run: () => Promise<string>;
}

export function UserPanel({
  user,
  isMe,
  onDirtyChange,
  onDone,
  onClose,
}: {
  user: StaffUser;
  isMe: boolean;
  onDirtyChange: (dirty: boolean) => void;
  /** Called with the sentence to show after an action succeeded. */
  onDone: (message: string) => Promise<void>;
  onClose: () => void;
}) {
  const [role, setRole] = useState<RoleKey>(user.role);
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const status = accountStatus(user);
  const id = { params: { path: { id: user.id } } };
  useReportDirty(onDirtyChange, role !== user.role);

  async function run(action: () => Promise<string>, inDialog: boolean) {
    setBusy(true);
    setError(null);
    setDialogError(null);
    try {
      const message = await action();
      setPending(null);
      await onDone(message);
    } catch (err) {
      const text = problemMessage(err, "Couldn't do that. Please try again.");
      if (inDialog) setDialogError(text);
      else setError(text);
    } finally {
      setBusy(false);
    }
  }

  const sendLink = () =>
    run(async () => {
      await call(api.POST("/api/v1/admin/users/{id}/send-reset", id));
      return status === "invited"
        ? `A new setup link is on its way to ${user.email}. Older links stop working.`
        : `A password reset link is on its way to ${user.email}. It works once and expires after 30 minutes.`;
    }, false);

  const unlock = () =>
    run(async () => {
      await call(api.POST("/api/v1/admin/users/{id}/unlock", id));
      return `${user.name} is unlocked and can sign in again. This is recorded in the audit log.`;
    }, false);

  const askRole = () =>
    setPending({
      title: `Make ${user.name} ${ROLE_LABELS[role] ?? role}?`,
      body:
        role === "super_admin"
          ? "A super-admin can do everything, including managing users and erasing a buyer's data. They are signed out and sign in again with the new role."
          : "They are signed out and sign in again with the new role. What they can see and do changes at once.",
      confirmLabel: "Change role",
      tone: role === "super_admin" ? "danger" : "default",
      run: async () => {
        await call(api.PATCH("/api/v1/admin/users/{id}", { ...id, body: { role } }));
        return `${user.name} is now ${ROLE_LABELS[role] ?? role}. They were signed out and sign in again with the new role.`;
      },
    });

  const askRevoke = () =>
    setPending({
      title: `Sign ${user.name} out everywhere?`,
      body: "Every device they are signed in on is signed out at once. Their password stays the same.",
      confirmLabel: "Sign out everywhere",
      tone: "default",
      run: async () => {
        await call(api.POST("/api/v1/admin/users/{id}/revoke-sessions", id));
        return `${user.name} is signed out on every device.`;
      },
    });

  const askResetTwoFactor = () =>
    setPending({
      title: `Reset ${user.name}'s two-factor?`,
      body: "Use this when they've lost their phone. Their two-factor and recovery codes are removed and they are signed out everywhere; they get a security email. If two-factor is required for their role, their next sign-in asks them to set it up again.",
      confirmLabel: "Reset two-factor",
      tone: "danger",
      run: async () => {
        await call(api.POST("/api/v1/admin/users/{id}/reset-2fa", id));
        return `${user.name}'s two-factor is reset and they are signed out everywhere.`;
      },
    });

  const askActive = () =>
    setPending(
      user.is_active
        ? {
            title: `Deactivate ${user.name}?`,
            body: "They are signed out everywhere and can't sign in until you reactivate the account. Their leads and history stay.",
            confirmLabel: "Deactivate account",
            tone: "danger",
            run: async () => {
              await call(
                api.PATCH("/api/v1/admin/users/{id}", { ...id, body: { is_active: false } }),
              );
              return `${user.name} is deactivated and signed out everywhere.`;
            },
          }
        : {
            title: `Reactivate ${user.name}?`,
            body: "They can sign in again with their existing password. If they've forgotten it, send a reset link after this.",
            confirmLabel: "Reactivate account",
            tone: "default",
            run: async () => {
              await call(
                api.PATCH("/api/v1/admin/users/{id}", { ...id, body: { is_active: true } }),
              );
              return `${user.name} is active again.`;
            },
          },
    );

  const lastSignIn = user.last_login_at ?? null;

  return (
    <section
      aria-labelledby="user-panel-title"
      className="flex min-w-0 flex-[1_1_320px] flex-col gap-4 rounded-card border border-gold-line-strong bg-noir-800 p-4"
    >
      <div>
        <h2 id="user-panel-title" className="text-[17px] font-bold [overflow-wrap:anywhere]">
          {user.name}
          {isMe ? <span className="font-normal text-muted"> (you)</span> : null}
        </h2>
        <p className="text-caption [overflow-wrap:anywhere] text-muted">{user.email}</p>
      </div>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-small">
        <dt className="text-muted">Status</dt>
        <dd className="text-ivory">{ACCOUNT_STATUS[status]}</dd>
        <dt className="text-muted">Two-factor</dt>
        <dd className="text-ivory">{twoFactorText(user)}</dd>
        <dt className="text-muted">Last sign-in</dt>
        <dd className="text-ivory">{lastSignIn ? formatDateTime(lastSignIn) : "Never"}</dd>
      </dl>
      <p className="text-caption text-muted">{addedText(user)}</p>

      {isMe ? (
        <Alert tone="info">
          This is your own account. Change your password and two-factor under My account; another
          super-admin can change your role.
        </Alert>
      ) : (
        <form
          aria-label={`Role of ${user.name}`}
          onSubmit={(event) => {
            event.preventDefault();
            if (role !== user.role) askRole();
          }}
          className="flex flex-wrap items-end gap-2.5"
        >
          <Select
            label="Role"
            value={role}
            options={ROLE_ORDER.map((key) => ({ value: key, label: ROLE_LABELS[key] ?? key }))}
            onChange={(event) =>
              setRole(ROLE_ORDER.find((key) => key === event.target.value) ?? user.role)
            }
            className="min-w-0 flex-[1_1_180px]"
          />
          <Button
            type="submit"
            variant="secondary"
            disabled={busy || role === user.role}
            className="mb-0.75"
          >
            Save role
          </Button>
        </form>
      )}

      <ul className="flex flex-col gap-2.5" aria-label={`Actions for ${user.name}`}>
        {status === "locked" ? (
          <li>
            <Button variant="secondary" loading={busy} onClick={() => void unlock()}>
              Unlock
            </Button>
          </li>
        ) : null}
        {user.is_active ? (
          <li className="flex flex-col gap-1">
            <Button variant="secondary" loading={busy} onClick={() => void sendLink()}>
              {status === "invited" ? "Send a new setup link" : "Send a password reset link"}
            </Button>
            <span className="text-caption text-muted">
              Emailed to them; you never see the link.
            </span>
          </li>
        ) : null}
        {!isMe && user.is_active ? (
          <li>
            <Button variant="secondary" disabled={busy} onClick={askRevoke}>
              Sign out everywhere
            </Button>
          </li>
        ) : null}
        {!isMe && user.two_factor_enabled ? (
          <li>
            <Button variant="danger" disabled={busy} onClick={askResetTwoFactor}>
              Reset two-factor
            </Button>
          </li>
        ) : null}
        {!isMe ? (
          <li>
            <Button
              variant={user.is_active ? "danger" : "secondary"}
              disabled={busy}
              onClick={askActive}
            >
              {user.is_active ? "Deactivate account" : "Reactivate account"}
            </Button>
          </li>
        ) : null}
      </ul>
      <div>
        <Button variant="tertiary" onClick={onClose}>
          Close
        </Button>
      </div>

      <ConfirmDialog
        open={pending !== null}
        title={pending?.title ?? ""}
        confirmLabel={pending?.confirmLabel ?? "Confirm"}
        tone={pending?.tone ?? "default"}
        busy={busy}
        error={dialogError}
        onCancel={() => {
          setPending(null);
          setDialogError(null);
        }}
        onConfirm={() => {
          if (pending) void run(pending.run, true);
        }}
      >
        {pending?.body}
      </ConfirmDialog>
    </section>
  );
}
