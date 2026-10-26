"use client";
/**
 * Sign-in (board NoirCmsLogin), in up to two steps:
 *   1. Email + password → POST /api/v1/auth/login. 200: signed in, on to the CMS. 202: the
 *      password was right, but the account has a second step (no session yet; the API set a
 *      5-minute HttpOnly `__Host-empire_2fa` cookie):
 *        - `verify`: the 6-digit code or a recovery code → POST /auth/2fa/verify;
 *        - `setup`: the `admin_2fa` flag is on and this admin has no two-factor yet, so it is set
 *          up now → POST /auth/2fa/enrol, then /auth/2fa/enrol/confirm, which also signs in and
 *          returns the recovery codes, shown once before going on.
 *   2. "Back", or a timed-out step, returns to the password form. During the set-up, Back is
 *      offered only until two-factor is confirmed: from then on the session exists and the
 *      recovery codes, shown once, must be saved first (review L7).
 *
 * SECURITY (handbook/SECURITY.md §1):
 * - Wrong email and wrong password show the SAME message, so the form never reveals which
 *   accounts exist. Keep it that way.
 * - After 5 failures (passwords and codes together) the API locks the account for 15 minutes on
 *   that network and answers 429; we show its text.
 * - Nothing is stored in localStorage/sessionStorage; the session is an HttpOnly cookie. Codes,
 *   keys and recovery codes live only in component memory and are never logged.
 */
import Link from "next/link";
import { useCallback, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Alert, Button, PasswordField, TextField } from "@empire/ui";
import { ProblemError, unwrap } from "@empire/api-client";
import { api, type Schema } from "@/lib/api";
import { DONE_MESSAGES, type DoneKind } from "@/lib/auth/links";
import { FORGOT_PATH } from "@/lib/routes";
import { AuthCard } from "@/components/admin/auth/AuthCard";
import { TwoFactorSetup } from "@/components/admin/auth/TwoFactorSetup";
import { secondStepOutcome, type VerifyOutcome } from "@/lib/auth/twoFactor";
import { TwoFactorCheck, type Proof } from "./TwoFactorCheck";

const WRONG_CREDENTIALS = "Email or password is incorrect.";
const LOCKED = "Too many attempts. Try again in 15 minutes.";
const UNREACHABLE = "We couldn't reach the server. Please try again.";
const HOME = "/admin";

type Challenge = Schema<"TwoFactorChallenge">;
type Step = { name: "password" } | { name: "verify" | "setup"; email: string };

export function LoginForm({ done }: { done: DoneKind | null }) {
  const router = useRouter();
  const [step, setStep] = useState<Step>({ name: "password" });
  const [notice, setNotice] = useState<string | null>(null);

  const back = useCallback((message?: string) => {
    setStep({ name: "password" });
    setNotice(message ?? null);
  }, []);

  const verify = useCallback(
    async (proof: Proof): Promise<VerifyOutcome> => {
      try {
        unwrap(await api.POST("/api/v1/auth/2fa/verify", { body: proof }));
        router.replace(HOME);
        return { result: "ok" };
      } catch (err) {
        return secondStepOutcome(err);
      }
    },
    [router],
  );

  const startEnrolment = useCallback(
    async () => unwrap(await api.POST("/api/v1/auth/2fa/enrol")),
    [],
  );
  const confirmEnrolment = useCallback(
    async (code: string) => {
      try {
        const answer = unwrap(await api.POST("/api/v1/auth/2fa/enrol/confirm", { body: { code } }));
        return answer.recovery_codes;
      } catch (err) {
        const outcome = secondStepOutcome(err);
        if (outcome.result === "expired") back(outcome.message);
        throw err;
      }
    },
    [back],
  );

  if (step.name === "verify") {
    return (
      <AuthCard eyebrow="STEP 2 OF 2" title="Two-factor check">
        <TwoFactorCheck email={step.email} verify={verify} onBack={back} />
      </AuthCard>
    );
  }
  if (step.name === "setup") {
    return (
      <AuthCard
        eyebrow="STEP 2 OF 2"
        title="Set up two-factor sign-in"
        intro="Admin accounts need a code from an authenticator app as well as the password. It takes a minute, once."
      >
        <TwoFactorSetup
          email={step.email}
          start={startEnrolment}
          confirm={confirmEnrolment}
          onDone={() => router.replace(HOME)}
          doneLabel="Continue to the CMS"
          // Only until two-factor is on: then the session exists and the codes must be saved.
          cancel={
            <Button variant="secondary" onClick={() => back()} className="w-full">
              Back
            </Button>
          }
        />
      </AuthCard>
    );
  }
  return (
    <AuthCard eyebrow="EMPIRE CMS" title="Staff sign-in">
      <PasswordStep
        done={done}
        notice={notice}
        onSignedIn={() => router.replace(HOME)}
        onChallenge={(challenge) => {
          setNotice(null);
          setStep({ name: challenge.step, email: challenge.email });
        }}
      />
    </AuthCard>
  );
}

function PasswordStep({
  done,
  notice,
  onSignedIn,
  onChallenge,
}: {
  done: DoneKind | null;
  notice: string | null;
  onSignedIn: () => void;
  onChallenge: (challenge: Challenge) => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ title: string; detail?: string } | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setError(null);
    setFieldErrors({});
    if (!email.trim() || !password) {
      setFieldErrors({
        email: email.trim() ? undefined : "Enter your email address.",
        password: password ? undefined : "Enter your password.",
      });
      return;
    }
    setBusy(true);
    try {
      const result = await api.POST("/api/v1/auth/login", {
        body: { email: email.trim(), password },
      });
      const answer = unwrap(result);
      setPassword("");
      if (result.response.status === 202) {
        setBusy(false);
        return onChallenge(answer as unknown as Challenge);
      }
      onSignedIn();
    } catch (err) {
      setBusy(false);
      if (err instanceof ProblemError) {
        if (err.status === 401) {
          return setError({
            title: WRONG_CREDENTIALS,
            detail:
              "Check both and try again. After 5 failed tries the account locks for 15 minutes.",
          });
        }
        if (err.status === 429) {
          return setError({
            title: err.problem.detail ?? LOCKED,
            detail: "If you need access sooner, ask the super-admin to unlock your account.",
          });
        }
        if (err.status === 422) {
          return setFieldErrors({
            email: err.fieldError("email") ? "Enter a valid email address." : undefined,
            password: err.fieldError("password") ? "Enter your password." : undefined,
          });
        }
      }
      setError({ title: UNREACHABLE });
    }
  }

  return (
    <form
      noValidate
      onSubmit={onSubmit}
      className="flex flex-col gap-5"
      aria-describedby={error ? "login-error" : undefined}
    >
      {done && !error && !notice ? <Alert tone="success">{DONE_MESSAGES[done]}</Alert> : null}
      {notice && !error ? <Alert tone="info">{notice}</Alert> : null}
      {error ? (
        <div id="login-error">
          <Alert tone="error" title={error.title}>
            {error.detail ?? null}
          </Alert>
        </div>
      ) : null}
      <TextField
        label="Email"
        name="email"
        type="email"
        autoComplete="username"
        inputMode="email"
        placeholder="name@empirebuildcon.com"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        error={fieldErrors.email}
      />
      <PasswordField
        label="Password"
        name="password"
        autoComplete="current-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        error={fieldErrors.password}
      />
      <div className="flex justify-end">
        <Link href={FORGOT_PATH} className="inline-flex min-h-11 items-center text-small font-bold">
          Forgot password?
        </Link>
      </div>
      <Button type="submit" loading={busy} className="w-full">
        Sign in
      </Button>
      <p className="text-caption text-muted">
        Sessions end after 8 hours without activity. Password reset links work once and expire after
        30 minutes.
      </p>
    </form>
  );
}
