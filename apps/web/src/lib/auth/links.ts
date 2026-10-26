/**
 * Rules for the setup and reset links the API emails (`/admin/setup#token=…`,
 * `/admin/reset#token=…`, users/service.py `setup_link`/`reset_link`), and the password policy
 * the forms check before sending (SECURITY.md §1: 12 to 200 characters; the API also refuses
 * common passwords and the account's own email, and its messages are shown as they come).
 *
 * SECURITY: the token is a one-time secret.
 * - It travels in the URL fragment (`#token=`), which browsers never send to a server, so it
 *   can't land in the web host's request logs (review L10). Links already sent with `?token=`
 *   still work: the query is read as a fallback.
 * - The page reads it once and removes it from the address bar straight away, wherever it was
 *   (`addressWithoutToken` + `history.replaceState`), keeps it in memory only and sends it in the
 *   request body, never in a URL. It never goes into a title, a log or storage.
 */

/** Shape of a link token: URL-safe base64, as long as the API's `PasswordReset.token` allows. */
const TOKEN_RE = /^[A-Za-z0-9_-]{16,200}$/;

function tokenIn(params: string): string | null {
  const token = new URLSearchParams(params).get("token");
  return token && TOKEN_RE.test(token) ? token : null;
}

/** The token in a query string ("?token=…"), or null when missing or malformed. */
export function tokenFromSearch(search: string): string | null {
  return tokenIn(search);
}

/**
 * The token of a link: from the fragment ("#token=…") first, else from the query ("?token=…",
 * links sent before the fragment was used). Null when missing or malformed.
 */
export function tokenFromLocation(hash: string, search: string): string | null {
  return tokenIn(hash.replace(/^#/, "")) ?? tokenIn(search);
}

/** True when the address still carries a token anywhere (query or fragment). */
export function hasToken(search: string, hash: string): boolean {
  return (
    new URLSearchParams(search).has("token") ||
    new URLSearchParams(hash.replace(/^#/, "")).has("token")
  );
}

/**
 * The same address without its `token`, in the query or the fragment (other parameters kept),
 * for `history.replaceState`, so the secret leaves the address bar, the history entry and any
 * bookmark or screenshot of the page.
 */
export function addressWithoutToken(pathname: string, search: string, hash = ""): string {
  const query = new URLSearchParams(search);
  query.delete("token");
  const fragment = new URLSearchParams(hash.replace(/^#/, ""));
  const fragmentHadToken = fragment.has("token");
  fragment.delete("token");
  const rest = query.toString();
  // A fragment that held the token is rebuilt from what is left; any other fragment is kept as is.
  const tail = fragmentHadToken ? (fragment.toString() ? `#${fragment.toString()}` : "") : hash;
  return `${pathname}${rest ? `?${rest}` : ""}${tail}`;
}

/** The API's password limits (users/passwords.py MIN_LENGTH / MAX_LENGTH). */
export const PASSWORD_MIN = 12;
export const PASSWORD_MAX = 200;

/**
 * Why a new password would be refused before it is sent, in the API's own words, or null.
 * WHY count code points: Python's `len()` counts them too, so "पासवर्ड…" is measured the same
 * way on both sides (an emoji is one character, not two).
 */
export function passwordProblem(password: string): string | null {
  const length = [...password].length;
  if (length < PASSWORD_MIN) return `Use at least ${PASSWORD_MIN} characters.`;
  if (length > PASSWORD_MAX) return `Use at most ${PASSWORD_MAX} characters.`;
  return null;
}

/** What the sign-in page says after a link was used (`/admin/login?done=setup|reset`). */
export const DONE_MESSAGES = {
  setup: "Your password is set. Sign in with your work email and the new password.",
  reset: "Your password is changed and you're signed out everywhere. Sign in with the new one.",
} as const;

export type DoneKind = keyof typeof DONE_MESSAGES;

/** The `done` value of the sign-in address, if it is one we know (anything else is ignored). */
export function doneKind(value: string | string[] | undefined): DoneKind | null {
  return value === "setup" || value === "reset" ? value : null;
}
