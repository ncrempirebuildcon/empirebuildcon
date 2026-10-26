"use client";
/**
 * My account → Two-factor sign-in (admins and super-admins): turn it on (your password, then
 * the key or QR code, a code from the app, and recovery codes shown once), turn it off (your
 * password and a code or recovery code), and make new recovery codes (a code or recovery code;
 * the old ones stop working).
 *
 * SECURITY (SECURITY.md §1): the key, QR code and recovery codes are shown only during the one
 * response that carries them and kept only in this component's memory. Passwords and codes are
 * cleared after each attempt. Turning it on signs out your other sessions (the API does it).
 * Wrong codes count toward the same lockout as passwords (D-027).
 */
import { useCallback, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Alert, Button, OneTimeCodeField, PasswordField, TextField } from "@empire/ui";
import { api, call } from "@/lib/api";
import { fieldErrors, problemMessage } from "@/lib/problems";
import { Panel } from "@/components/admin/states";
import { RecoveryCodes } from "@/components/admin/auth/RecoveryCodes";
import { TwoFactorSetup } from "@/components/admin/auth/TwoFactorSetup";
import { useReportDirty } from "@/components/admin/useUnsavedChanges";
import { useAdminSession } from "../session-context";

type Mode =
  | { name: "idle" }
  | { name: "password"; error?: string }
  | { name: "setup" }
  | { name: "disable" }
  | { name: "regenerate" }
  | { name: "codes"; codes: string[] };

export function TwoFactorPanel({ onDirtyChange }: { onDirtyChange: (dirty: boolean) => void }) {
  const router = useRouter();
  const { me } = useAdminSession();
  const [mode, setMode] = useState<Mode>({ name: "idle" });
  const [message, setMessage] = useState<string | null>(null);
  const enabled = me.two_factor_enabled;
  const left = me.recovery_codes_left;
  // Open steps hold something worth keeping (a key being scanned, codes not yet saved).
  useReportDirty(onDirtyChange, mode.name === "setup" || mode.name === "codes");

  const finish = useCallback(
    (text: string) => {
      setMode({ name: "idle" });
      setMessage(text);
      // The shell's `me` comes from the server: read it again so "On"/"Off" and counts update.
      router.refresh();
    },
    [router],
  );

  // WHY a ref: the password is needed once, by `start`, and then dropped; it never has to
  // re-render anything, and a ref keeps it out of React state.
  const passwordRef = useRef("");
  const start = useCallback(async () => {
    const current_password = passwordRef.current;
    passwordRef.current = ""; // SECURITY: not needed after this request
    try {
      return await call(api.POST("/api/v1/auth/2fa/setup", { body: { current_password } }));
    } catch (err) {
      // A wrong password goes back to the password step, with the API's words at the field.
      const message = fieldErrors(err).current_password;
      if (message) setMode({ name: "password", error: message });
      throw err;
    }
  }, []);
  const confirm = useCallback(
    async (code: string) =>
      (await call(api.POST("/api/v1/auth/2fa/setup/confirm", { body: { code } }))).recovery_codes,
    [],
  );

  if (!me.can_use_two_factor) {
    return (
      <Panel id="two-factor" title="Two-factor sign-in">
        <p className="text-small text-muted">
          Two-factor sign-in is for admin and super-admin accounts. Your role signs in with the
          password only.
        </p>
      </Panel>
    );
  }

  return (
    <Panel
      id="two-factor"
      title="Two-factor sign-in"
      description={
        me.two_factor_required
          ? "Required for your role: the admin_2fa setting is on."
          : "Asks for a code from an authenticator app after your password."
      }
    >
      <p className="text-small">
        Status: <strong className="text-ivory">{enabled ? "On" : "Off"}</strong>
        {enabled && typeof left === "number" ? (
          <span className="text-muted">
            {" "}
            · {left} recovery {left === 1 ? "code" : "codes"} left
          </span>
        ) : null}
      </p>
      {message ? <Alert tone="success">{message}</Alert> : null}
      {enabled && typeof left === "number" && left <= 3 && mode.name === "idle" ? (
        <Alert tone="info">Only {left} recovery codes are left. Make new ones and save them.</Alert>
      ) : null}

      {mode.name === "idle" ? (
        <div className="flex flex-wrap gap-2.5">
          {enabled ? (
            <>
              <Button variant="secondary" onClick={() => setMode({ name: "regenerate" })}>
                New recovery codes
              </Button>
              <Button variant="danger" onClick={() => setMode({ name: "disable" })}>
                Turn off two-factor
              </Button>
            </>
          ) : (
            <Button onClick={() => (setMessage(null), setMode({ name: "password" }))}>
              Turn on two-factor
            </Button>
          )}
        </div>
      ) : null}

      {mode.name === "password" ? (
        <PasswordFirst
          initialError={mode.error}
          onCancel={() => setMode({ name: "idle" })}
          onContinue={(password) => {
            passwordRef.current = password;
            setMode({ name: "setup" });
          }}
        />
      ) : null}
      {mode.name === "setup" ? (
        <div className="flex max-w-xl flex-col gap-4">
          <TwoFactorSetup
            email={me.email}
            start={start}
            confirm={confirm}
            headingLevel={3}
            // Two-factor is on from here: read `me` again so the status is right whatever happens.
            onConfirmed={() => router.refresh()}
            onDone={() => finish("Two-factor sign-in is on. Your other devices were signed out.")}
            doneLabel="Done"
            cancel={
              <div>
                <Button variant="secondary" onClick={() => setMode({ name: "idle" })}>
                  Cancel
                </Button>
              </div>
            }
          />
        </div>
      ) : null}
      {mode.name === "disable" ? (
        <ProofForm
          label="Turn off two-factor"
          withPassword
          submitLabel="Turn off two-factor"
          danger
          onCancel={() => setMode({ name: "idle" })}
          send={async (proof, password) => {
            await call(
              api.POST("/api/v1/auth/2fa/disable", {
                body: { ...proof, current_password: password ?? "" },
              }),
            );
            finish("Two-factor sign-in is off. Your recovery codes no longer work.");
          }}
        />
      ) : null}
      {mode.name === "regenerate" ? (
        <ProofForm
          label="New recovery codes"
          submitLabel="Make new codes"
          onCancel={() => setMode({ name: "idle" })}
          send={async (proof) => {
            const answer = await call(api.POST("/api/v1/auth/2fa/recovery-codes", { body: proof }));
            setMode({ name: "codes", codes: answer.recovery_codes });
          }}
        />
      ) : null}
      {mode.name === "codes" ? (
        <div className="flex max-w-xl flex-col gap-3">
          <h3 className="text-lg font-bold">Your new recovery codes</h3>
          <RecoveryCodes
            codes={mode.codes}
            email={me.email}
            doneLabel="Done"
            onDone={() => finish("New recovery codes are ready. The old ones no longer work.")}
          />
        </div>
      ) : null}
    </Panel>
  );
}

/** Turning two-factor on starts with the password (the API checks it before making a key). */
function PasswordFirst({
  initialError,
  onCancel,
  onContinue,
}: {
  initialError?: string;
  onCancel: () => void;
  onContinue: (password: string) => void;
}) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | undefined>(initialError);
  return (
    <form
      noValidate
      aria-label="Confirm your password"
      onSubmit={(event) => {
        event.preventDefault();
        if (!password) return setError("Enter your current password.");
        onContinue(password);
      }}
      className="flex max-w-md flex-col gap-4"
    >
      <PasswordField
        label="Current password"
        autoComplete="current-password"
        toggleNoun="current password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        error={error}
        hint="To keep someone at your desk from turning it on for you."
      />
      <div className="flex flex-wrap gap-2.5">
        <Button type="submit">Continue</Button>
        <Button variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

type ProofBody = { code: string } | { recovery_code: string };

/** A code from the app or a recovery code (and, to turn it off, the password). */
function ProofForm({
  label,
  submitLabel,
  withPassword = false,
  danger = false,
  onCancel,
  send,
}: {
  label: string;
  submitLabel: string;
  withPassword?: boolean;
  danger?: boolean;
  onCancel: () => void;
  send: (proof: ProofBody, password?: string) => Promise<void>;
}) {
  const [password, setPassword] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<{ password?: string; proof?: string }>({});

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const found = {
      password: withPassword && !password ? "Enter your current password." : undefined,
      proof: useRecovery
        ? recovery.trim()
          ? undefined
          : "Enter one of your recovery codes."
        : code.length === 6
          ? undefined
          : "Enter the 6 digits from your authenticator app.",
    };
    setErrors(found);
    setError(null);
    if (found.password || found.proof) return;
    setBusy(true);
    try {
      await send(useRecovery ? { recovery_code: recovery.trim() } : { code }, password);
    } catch (err) {
      const fields = fieldErrors(err);
      setErrors({
        password: fields.current_password,
        proof: fields.code ?? fields.recovery_code,
      });
      setError(problemMessage(err, "That didn't work. Check the code and try again."));
    } finally {
      setBusy(false);
      setCode("");
      setRecovery("");
      setPassword("");
    }
  }

  return (
    <form
      noValidate
      aria-label={label}
      onSubmit={onSubmit}
      className="flex max-w-md flex-col gap-4"
    >
      {error ? <Alert tone="error">{error}</Alert> : null}
      {withPassword ? (
        <PasswordField
          label="Current password"
          autoComplete="current-password"
          toggleNoun="current password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={errors.password}
        />
      ) : null}
      {useRecovery ? (
        <TextField
          label="Recovery code"
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={40}
          value={recovery}
          onChange={(event) => setRecovery(event.target.value)}
          error={errors.proof}
          hint="Each recovery code works once."
          inputClassName="font-mono tracking-wider"
        />
      ) : (
        <OneTimeCodeField
          label="6-digit code from the app"
          value={code}
          onValueChange={setCode}
          error={errors.proof}
        />
      )}
      <Button
        variant="tertiary"
        className="min-h-11 self-start"
        onClick={() => {
          setUseRecovery((value) => !value);
          setErrors({});
        }}
      >
        {useRecovery ? "Use a code from the app instead" : "Use a recovery code"}
      </Button>
      <div className="flex flex-wrap gap-2.5">
        <Button type="submit" variant={danger ? "danger" : "primary"} loading={busy}>
          {submitLabel}
        </Button>
        <Button variant="secondary" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
