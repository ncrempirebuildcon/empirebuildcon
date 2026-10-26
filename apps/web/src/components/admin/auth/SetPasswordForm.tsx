"use client";
/**
 * Choose a password from an emailed link: /admin/setup#token=… (a new account) and
 * /admin/reset#token=… (a forgotten password); `?token=` still works for older links. Both call
 * POST /api/v1/auth/password/reset with
 * the token and the new password; the API signs the account out everywhere and burns every
 * other open link.
 *
 * How it works:
 *   1. The token is read from the address once, when the form first renders in the browser
 *      (`SetPasswordPage` loads this file with `ssr: false`, so the server never renders it).
 *      It is in the fragment, which never reaches a server (review L10).
 *   2. Straight after, an effect removes it from the address bar with `history.replaceState`.
 *      Reloading the page afterwards shows "This link is incomplete", which is the safe outcome.
 *   3. The password is checked for length here (the API's wording), then sent; the API's own
 *      policy messages (too common, same as the email) are shown at the field.
 *   4. On success the browser goes to sign-in with a clear message (`?done=setup|reset`).
 *
 * SECURITY (SECURITY.md §1): the token lives only in this component's memory. It is never
 * logged, stored, put in a title or sent in a URL; the page sends `Referrer-Policy: no-referrer`
 * (next.config.ts and the page's metadata) and loads nothing from other sites.
 */
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Alert, Button, PasswordField } from "@empire/ui";
import { ProblemError, unwrap } from "@empire/api-client";
import { api } from "@/lib/api";
import {
  PASSWORD_MIN,
  addressWithoutToken,
  hasToken,
  passwordProblem,
  tokenFromLocation,
  type DoneKind,
} from "@/lib/auth/links";
import { FORGOT_PATH, SIGN_IN_PATH } from "@/lib/routes";

const UNREACHABLE = "We couldn't reach the server. Please try again.";

export interface SetPasswordFormProps {
  /** "setup": first password for a new account; "reset": a new password. */
  purpose: DoneKind;
}

export function SetPasswordForm({ purpose }: SetPasswordFormProps) {
  const router = useRouter();
  // 1. Read once, in the browser only (this component is never server-rendered): the fragment
  //    first, the query for links sent before the fragment was used.
  const [token] = useState(() => tokenFromLocation(window.location.hash, window.location.search));
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [linkInvalid, setLinkInvalid] = useState(false);
  const [fieldError, setFieldError] = useState<string | undefined>();

  // 2. SECURITY: take the token out of the address bar and this history entry at once.
  useEffect(() => {
    const { pathname, search, hash } = window.location;
    if (hasToken(search, hash)) {
      window.history.replaceState(
        window.history.state,
        "",
        addressWithoutToken(pathname, search, hash),
      );
    }
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !token) return;
    setError(null);
    const problem = passwordProblem(password); // 3
    setFieldError(problem ?? undefined);
    if (problem) return;
    setBusy(true);
    try {
      unwrap(
        await api.POST("/api/v1/auth/password/reset", {
          body: { token, new_password: password },
        }),
      );
      router.replace(`${SIGN_IN_PATH}?done=${purpose}`); // 4
    } catch (err) {
      setBusy(false);
      if (err instanceof ProblemError && err.status === 422) {
        const messages = (err.problem.errors ?? [])
          .filter((item) => item.field === "new_password")
          .map((item) => item.message.replace(/^Value error, /, ""));
        setFieldError(messages.join(" ") || "Choose a different password.");
      } else if (err instanceof ProblemError && err.status === 400) {
        setLinkInvalid(true);
      } else if (err instanceof ProblemError && err.status === 429) {
        setError(err.problem.detail ?? "Too many attempts. Try again later.");
      } else {
        setError(UNREACHABLE);
      }
    }
  }

  if (!token || linkInvalid) {
    return (
      <div className="flex flex-col gap-5">
        <Alert
          tone="error"
          title={token ? "This link has expired or was used already" : "This link is incomplete"}
        >
          {token
            ? "Each link works once and only for a limited time. Ask for a new one."
            : "Open the link from the email again, or ask for a new one. For your safety the link is removed from the address bar as soon as the page opens, so reloading it doesn't work."}
        </Alert>
        <Link href={FORGOT_PATH} className="text-small font-bold">
          Ask for a new link
        </Link>
        <Link href={SIGN_IN_PATH} className="text-small font-bold">
          Back to sign-in
        </Link>
      </div>
    );
  }

  return (
    <form noValidate onSubmit={onSubmit} className="flex flex-col gap-5">
      {error ? <Alert tone="error">{error}</Alert> : null}
      <PasswordField
        label={purpose === "setup" ? "Choose a password" : "New password"}
        name="new-password"
        autoComplete="new-password"
        toggleNoun="password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        hint={`At least ${PASSWORD_MIN} characters. A short sentence you'll remember works well; no symbols needed.`}
        error={fieldError}
      />
      <Button type="submit" loading={busy} className="w-full">
        {purpose === "setup" ? "Set password" : "Change password"}
      </Button>
      <p className="text-caption text-muted">
        {purpose === "setup"
          ? "This link works once. After this you sign in with your work email and this password."
          : "This link works once. Saving signs you out on every device."}
      </p>
    </form>
  );
}
