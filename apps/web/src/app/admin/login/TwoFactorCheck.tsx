"use client";
/**
 * Sign-in step 2 (board NoirCmsLogin, "Two-factor check"): the 6-digit code from the
 * authenticator app, or "Use a recovery code" instead, and Back to the password step.
 *
 * SECURITY (SECURITY.md §1, D-027): the API counts every wrong code on the same lockout as
 * passwords, so after 5 failures it answers 429 and we show its text. A timed-out step (the
 * 5-minute sign-in cookie expired) sends the person back to the password step with the API's
 * sentence. The code is cleared after every attempt and never kept.
 */
import { useState, type FormEvent } from "react";
import { Alert, Button, OneTimeCodeField, TextField } from "@empire/ui";
import type { VerifyOutcome } from "@/lib/auth/twoFactor";

export type Proof = { code: string } | { recovery_code: string };

export type { VerifyOutcome } from "@/lib/auth/twoFactor";

export function TwoFactorCheck({
  email,
  verify,
  onBack,
}: {
  email: string;
  verify: (proof: Proof) => Promise<VerifyOutcome>;
  onBack: (message?: string) => void;
}) {
  const [useRecovery, setUseRecovery] = useState(false);
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState("");
  const [busy, setBusy] = useState(false);
  const [fieldError, setFieldError] = useState<string | undefined>();
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setError(null);
    if (!useRecovery && code.length !== 6) {
      return setFieldError("Enter the 6 digits from your authenticator app.");
    }
    if (useRecovery && !recovery.trim()) return setFieldError("Enter one of your recovery codes.");
    setFieldError(undefined);
    setBusy(true);
    const outcome = await verify(useRecovery ? { recovery_code: recovery.trim() } : { code });
    setBusy(false);
    setCode("");
    setRecovery("");
    if (outcome.result === "ok") return;
    if (outcome.result === "expired") return onBack(outcome.message);
    if (outcome.result === "wrong") {
      return setFieldError(
        outcome.message ??
          (useRecovery
            ? "That recovery code isn't right, or it was used already."
            : "That code isn't right. Check your authenticator app and try again."),
      );
    }
    setError(outcome.message ?? "We couldn't reach the server. Please try again.");
  }

  return (
    <form noValidate onSubmit={onSubmit} className="flex flex-col gap-4">
      {error ? <Alert tone="error">{error}</Alert> : null}
      <p className="text-cms-body">
        {useRecovery
          ? "Enter one of the recovery codes you saved for "
          : "Enter the 6-digit code from your authenticator app for "}
        <strong className="[overflow-wrap:anywhere] text-ivory">{email}</strong>.
      </p>
      {useRecovery ? (
        <TextField
          label="Recovery code"
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={40}
          value={recovery}
          onChange={(event) => setRecovery(event.target.value)}
          error={fieldError}
          hint="Each recovery code works once."
          inputClassName="font-mono tracking-wider"
        />
      ) : (
        <OneTimeCodeField
          label="6-digit code"
          value={code}
          onValueChange={setCode}
          error={fieldError}
        />
      )}
      <Button type="submit" loading={busy} className="w-full">
        Verify and continue
      </Button>
      <Button
        variant="tertiary"
        onClick={() => {
          setUseRecovery((value) => !value);
          setFieldError(undefined);
          setCode("");
          setRecovery("");
        }}
        className="min-h-11 self-center"
      >
        {useRecovery ? "Use a code from the app instead" : "Use a recovery code"}
      </Button>
      <Button variant="secondary" onClick={() => onBack()} disabled={busy} className="w-full">
        Back
      </Button>
      <div className="flex gap-2.5 rounded-tile border-l-3 border-gold-500 bg-noir-700 px-3.5 py-3 text-caption">
        <svg
          aria-hidden="true"
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          className="mt-0.5 shrink-0 text-gold-400"
        >
          <path d="M12 3l7 3v5c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6l7-3z" />
        </svg>
        <span>
          Two-factor applies to admin and super-admin accounts (setting{" "}
          <code className="text-gold-300">admin_2fa</code>). Lost your phone? Use a recovery code,
          or ask the super-admin to reset your two-factor.
        </span>
      </div>
    </form>
  );
}
