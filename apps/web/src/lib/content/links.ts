/**
 * Link checks for content forms (CTA blocks, hero buttons, offer buttons, redirects), the same
 * rules the API applies, so staff see the problem next to the field before saving.
 *
 * SECURITY: the API is the guard (it refuses the same links); this only explains early.
 * A link is either a path on this site ("/projects", "/contact#visit") or a full https:// address.
 * Script-like schemes (javascript:, data:, vbscript:, file:) and protocol-relative "//host" links
 * are refused, so a button can never run code or leave the site without saying so.
 */

const SCRIPT_SCHEME = /^\s*(javascript|data|vbscript|file)\s*:/i;

/** True for a path on this site: starts with one "/", no spaces, no backslashes. */
export function isInternalPath(value: string): boolean {
  return /^\/(?!\/)[^\s\\]*$/.test(value);
}

/**
 * True for a full https:// address with a host and no user name or password.
 * WHY no user info: "https://empirebuildcon.com@other.example" really goes to other.example.
 */
export function isHttpsUrl(value: string): boolean {
  if (/[\s\\]/.test(value)) return false;
  try {
    const url = new URL(value);
    return (
      url.protocol === "https:" && url.hostname !== "" && url.username === "" && url.password === ""
    );
  } catch {
    return false;
  }
}

/**
 * The problem with a button link, or null when it is fine. Empty is fine here; callers that need
 * a link say so themselves.
 */
export function linkProblem(raw: string): string | null {
  const value = raw.trim();
  if (value === "") return null;
  if (SCRIPT_SCHEME.test(value)) {
    return "Links that run code (javascript:, data: and similar) aren't allowed.";
  }
  if (isInternalPath(value) || isHttpsUrl(value)) return null;
  if (value.startsWith("//")) return "Start a page on this site with a single /, e.g. /projects.";
  if (/^http:\/\//i.test(value)) return "Use a secure https:// address.";
  return "Use a page on this site (starting with /, e.g. /contact) or a full https:// address.";
}

/**
 * The problem with a redirect path ("from" side): a path on this site with no query string.
 */
export function redirectFromProblem(raw: string): string | null {
  const value = raw.trim();
  if (value === "") return "Enter the old address, starting with /.";
  if (!isInternalPath(value)) return "Start with / and use no spaces, e.g. /old-page.";
  if (value.includes("?")) return "Leave out the query string (the part after ?).";
  if (value.includes("#")) return "Leave out the part after #; browsers never send it.";
  return null;
}
