"use client";
/**
 * Invite a staff member (board NoirCmsUsers, "+ Invite user"): POST /api/v1/admin/users. The API
 * emails them a single-use setup link; nobody types, sees or shares their password, and the API
 * never returns the link.
 */
import { useState, type FormEvent } from "react";
import { Alert, Button, Select, TextField } from "@empire/ui";
import { api, call, type Schema } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/labels";
import { fieldErrors, problemMessage, type FieldErrors } from "@/lib/problems";
import { INVITE_ROLES, type RoleKey } from "@/lib/users";
import { useReportDirty } from "@/components/admin/useUnsavedChanges";

type User = Schema<"User">;

export function InviteForm({
  onInvited,
  onDirtyChange,
}: {
  onInvited: (user: User) => void;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<RoleKey>("sales");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});
  useReportDirty(onDirtyChange, email !== "" || name !== "");

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const found: FieldErrors = {};
    if (!email.trim()) found.email = "Enter their work email.";
    if (!name.trim()) found.name = "Enter their name as colleagues know it.";
    setErrors(found);
    setError(null);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    try {
      const user = await call(
        api.POST("/api/v1/admin/users", {
          body: { email: email.trim(), name: name.trim(), role, is_active: true },
        }),
      );
      setEmail("");
      setName("");
      onInvited(user);
    } catch (err) {
      setErrors(fieldErrors(err));
      setError(problemMessage(err, "Couldn't send the invite."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      noValidate
      aria-label="Invite a user"
      onSubmit={onSubmit}
      className="flex flex-col gap-4 rounded-card border border-gold-line-strong bg-noir-800 p-5"
    >
      {error ? <Alert tone="error">{error}</Alert> : null}
      <fieldset disabled={busy} className="flex min-w-0 flex-wrap items-start gap-4">
        <legend className="sr-only">Invite a user</legend>
        <TextField
          label="Work email"
          type="email"
          autoComplete="off"
          inputMode="email"
          placeholder="name@empirebuildcon.com"
          maxLength={254}
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={errors.email}
          className="min-w-0 flex-[1.4_1_260px]"
        />
        <TextField
          label="Name"
          autoComplete="off"
          maxLength={80}
          value={name}
          onChange={(event) => setName(event.target.value)}
          error={errors.name}
          className="min-w-0 flex-[1_1_200px]"
        />
        <Select
          label="Role"
          value={role}
          options={INVITE_ROLES.map((key) => ({ value: key, label: ROLE_LABELS[key] ?? key }))}
          onChange={(event) =>
            setRole(INVITE_ROLES.find((key) => key === event.target.value) ?? "sales")
          }
          error={errors.role}
          className="min-w-0 flex-[1_1_180px]"
        />
      </fieldset>
      <div className="flex flex-wrap items-center gap-4">
        <Button type="submit" loading={busy}>
          Send invite link
        </Button>
        <p className="min-w-0 flex-[1_1_260px] text-caption text-muted">
          They set their own password (12 characters or more) from a single-use email link. Admins
          never type, see or share passwords. Two-factor sign-in is asked of admins once the{" "}
          <code className="text-gold-300">admin_2fa</code> flag is on.
        </p>
      </div>
    </form>
  );
}
