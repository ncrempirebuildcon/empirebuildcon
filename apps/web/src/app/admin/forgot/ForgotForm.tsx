"use client";
/**
 * "Forgot password?" form: email → POST /api/v1/auth/password/forgot (204 whatever the email).
 *
 * SECURITY (SECURITY.md §1): the page shows the SAME message for every email, so it never
 * reveals which addresses have accounts. The API answers 204 either way and rate-limits by email
 * and by network before looking the account up, so its 429 says nothing about the account either.
 * The address is not kept after sending (the field is cleared), and nothing is stored in the
 * browser.
 */
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Alert, Button, TextField } from "@empire/ui";
import { ProblemError, unwrap } from "@empire/api-client";
import { api } from "@/lib/api";
import { SIGN_IN_PATH } from "@/lib/routes";

const SENT_MESSAGE =
  "If that email belongs to a staff account, a reset link is on its way. It works once and expires after 30 minutes. Check the spam folder if it doesn't arrive within a few minutes.";
const UNREACHABLE = "We couldn't reach the server. Please try again.";

export function ForgotForm() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | undefined>();

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setError(null);
    setFieldError(undefined);
    const address = email.trim();
    if (!address) return setFieldError("Enter your work email.");
    setBusy(true);
    try {
      unwrap(await api.POST("/api/v1/auth/password/forgot", { body: { email: address } }));
      setSent(true);
      setEmail("");
    } catch (err) {
      if (err instanceof ProblemError && err.status === 422) {
        setFieldError("Enter a valid email address, like name@empirebuildcon.com.");
      } else if (err instanceof ProblemError && err.status === 429) {
        setError(err.problem.detail ?? "Too many reset requests. Try again in an hour.");
      } else {
        setError(UNREACHABLE);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      {sent ? (
        <Alert tone="success" title="Check your email">
          {SENT_MESSAGE}
        </Alert>
      ) : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      <form noValidate onSubmit={onSubmit} className="flex flex-col gap-5">
        <TextField
          label="Work email"
          name="email"
          type="email"
          autoComplete="username"
          inputMode="email"
          placeholder="name@empirebuildcon.com"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={fieldError}
        />
        <Button type="submit" loading={busy} className="w-full">
          {sent ? "Send another link" : "Send reset link"}
        </Button>
      </form>
      <p className="text-caption text-muted">
        No access to that inbox, or locked out? Ask the super-admin to send you a new link.
      </p>
      <Link href={SIGN_IN_PATH} className="text-small font-bold">
        Back to sign-in
      </Link>
    </div>
  );
}
