"use client";
/**
 * Sign-in form: email + password → POST /api/v1/auth/login, then the CMS shell.
 *
 * SECURITY (handbook/SECURITY.md §1):
 * - Wrong email and wrong password show the SAME message, so the form never reveals which
 *   accounts exist. Keep it that way.
 * - After 5 failures the API locks the account for 15 minutes and answers 429; we show its text.
 * - Nothing is stored in localStorage/sessionStorage; the session is an HttpOnly cookie.
 */
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Alert, Button, TextField } from "@empire/ui";
import { ProblemError, unwrap } from "@empire/api-client";
import { api } from "@/lib/api";

const WRONG_CREDENTIALS = "Email or password is incorrect.";
const LOCKED = "Too many attempts. Try again in 15 minutes.";
const UNREACHABLE = "We couldn't reach the server. Please try again.";

export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
      unwrap(await api.POST("/api/v1/auth/login", { body: { email: email.trim(), password } }));
      router.replace("/admin");
    } catch (err) {
      setBusy(false);
      if (err instanceof ProblemError) {
        if (err.status === 401) return setError(WRONG_CREDENTIALS);
        if (err.status === 429) return setError(err.problem.detail ?? LOCKED);
        if (err.status === 422) {
          return setFieldErrors({
            email: err.fieldError("email") ? "Enter a valid email address." : undefined,
            password: err.fieldError("password") ? "Enter your password." : undefined,
          });
        }
      }
      setError(UNREACHABLE);
    }
  }

  return (
    <form
      noValidate
      onSubmit={onSubmit}
      className="flex flex-col gap-5"
      aria-describedby={error ? "login-error" : undefined}
    >
      {error ? (
        <div id="login-error">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}
      <TextField
        label="Email"
        name="email"
        type="email"
        autoComplete="username"
        inputMode="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        error={fieldErrors.email}
      />
      <TextField
        label="Password"
        name="password"
        type={showPassword ? "text" : "password"}
        autoComplete="current-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        error={fieldErrors.password}
        trailing={
          <button
            type="button"
            onClick={() => setShowPassword((v) => !v)}
            aria-pressed={showPassword}
            aria-label={showPassword ? "Hide password" : "Show password"}
            className="min-h-11 rounded-input px-3 text-small font-bold text-gold-400 hover:text-gold-300"
          >
            {showPassword ? "Hide" : "Show"}
          </button>
        }
      />
      <Button type="submit" loading={busy} className="w-full">
        Sign in
      </Button>
      <p className="text-caption text-muted">
        Forgot your password? Ask a super-admin to send you a reset link.
      </p>
    </form>
  );
}
