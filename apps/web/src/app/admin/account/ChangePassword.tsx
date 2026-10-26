"use client";
/**
 * Change your own password (POST /api/v1/auth/password/change). The API checks the current
 * password, applies the same policy as setup links, and signs out every OTHER session; this one
 * stays signed in.
 *
 * SECURITY: both fields are cleared after a successful change; nothing is kept in the browser.
 * A wrong current password is a 400 with the API's sentence, shown at that field.
 */
import { useState, type FormEvent } from "react";
import { Alert, Button, PasswordField } from "@empire/ui";
import { ProblemError } from "@empire/api-client";
import { api, call } from "@/lib/api";
import { PASSWORD_MIN, passwordProblem } from "@/lib/auth/links";
import { problemMessage } from "@/lib/problems";
import { Panel } from "@/components/admin/states";
import { useReportDirty } from "@/components/admin/useUnsavedChanges";

export function ChangePassword({ onDirtyChange }: { onDirtyChange: (dirty: boolean) => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<{ current?: string; next?: string }>({});
  useReportDirty(onDirtyChange, current !== "" || next !== "");

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setDone(false);
    setError(null);
    const found = {
      current: current ? undefined : "Enter your current password.",
      next: passwordProblem(next) ?? undefined,
    };
    setErrors(found);
    if (found.current || found.next) return;
    setBusy(true);
    try {
      await call(
        api.POST("/api/v1/auth/password/change", {
          body: { current_password: current, new_password: next },
        }),
      );
      setCurrent("");
      setNext("");
      setDone(true);
    } catch (err) {
      if (err instanceof ProblemError && err.status === 400) {
        setErrors({ current: err.problem.detail ?? "Your current password is not correct." });
      } else if (err instanceof ProblemError && err.status === 422) {
        const messages = (err.problem.errors ?? [])
          .filter((item) => item.field === "new_password")
          .map((item) => item.message.replace(/^Value error, /, ""));
        setErrors({ next: messages.join(" ") || "Choose a different password." });
      } else {
        setError(problemMessage(err, "Couldn't change your password."));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel
      id="password"
      title="Password"
      description="Changing it signs you out on every other device. This one stays signed in."
    >
      {done ? (
        <Alert tone="success">Your password is changed. Other devices are signed out.</Alert>
      ) : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      <form
        noValidate
        onSubmit={onSubmit}
        aria-label="Change password"
        className="flex max-w-md flex-col gap-4"
      >
        <PasswordField
          label="Current password"
          name="current-password"
          autoComplete="current-password"
          toggleNoun="current password"
          value={current}
          onChange={(event) => setCurrent(event.target.value)}
          error={errors.current}
        />
        <PasswordField
          label="New password"
          name="new-password"
          autoComplete="new-password"
          toggleNoun="new password"
          value={next}
          onChange={(event) => setNext(event.target.value)}
          hint={`At least ${PASSWORD_MIN} characters. A short sentence you'll remember works well.`}
          error={errors.next}
        />
        <div>
          <Button type="submit" loading={busy}>
            Change password
          </Button>
        </div>
      </form>
    </Panel>
  );
}
