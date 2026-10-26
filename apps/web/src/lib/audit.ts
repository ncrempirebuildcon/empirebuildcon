/**
 * Reading audit-log entries (`GET /admin/audit-log`, schema `AuditEntry`) for the Audit log
 * screen (board NoirCmsAudit): the board's six kinds of action for the chips, plain words for an
 * action, and the before/after lines of an entry's `changes`.
 *
 * `changes` is written by apps/api platform/audit.py: `{field: [before, after]}` for an edit
 * (`audit.diff`), or `{field: value}` for facts about the event (an export's filters, a count).
 * INVARIANT (API side): it never holds passwords, tokens, full phone numbers or personal free
 * text (notes show "[hidden]"), so the screen can show it as it is.
 */

/** The board's action chips. "other" covers everything the six don't name. */
export const AUDIT_KINDS = {
  login: "Login",
  publish: "Publish",
  update: "Update",
  export: "Export",
  permission: "Permission",
  erasure: "Erasure",
} as const;

export type AuditKind = keyof typeof AUDIT_KINDS | "other";

// WHY lists and not a regex per kind: each list is short and reads like the board's wording.
const PERMISSION_ACTIONS = new Set([
  "user.created",
  "user.updated",
  "user.unlocked",
  "user.sessions_revoked",
  "user.reset_link_sent",
  "user.two_factor_reset",
  "flag.changed",
]);

/** Which chip an action belongs to (board NoirCmsAudit: Login, Publish, Update, …). */
export function auditKind(action: string): AuditKind {
  if (action.startsWith("auth.") || action === "user.locked") return "login";
  if (action === "lead.erased" || action.endsWith(".erased")) return "erasure";
  if (action.endsWith(".exported")) return "export";
  if (PERMISSION_ACTIONS.has(action)) return "permission";
  if (/\.(published|unpublished|archived|restored|scheduled_publish_cancelled)$/.test(action)) {
    return "publish";
  }
  if (
    /\.(created|updated|deleted|reordered|saved|set|attached|detached|replaced|uploaded|duplicated|note_added|blocks_saved|amenities_set|block_reference_removed|changed)$/.test(
      action,
    )
  )
    return "update";
  return "other";
}

const VERBS: Record<string, string> = {
  created: "created",
  updated: "changed",
  deleted: "deleted",
  published: "published",
  unpublished: "unpublished",
  reordered: "reordered",
  exported: "exported",
  erased: "erased",
  archived: "archived",
  restored: "restored",
};

/** Exact wording for actions whose generic "<thing> <verb>" would read oddly. */
const ACTION_WORDS: Record<string, string> = {
  "auth.login": "Signed in",
  "auth.logout": "Signed out",
  "auth.login_failed": "Sign-in failed",
  "auth.two_factor_failed": "Two-factor code refused",
  "auth.two_factor_requested": "Password right, code asked",
  "auth.password_check_failed": "Password check failed",
  "user.locked": "Account locked",
  "user.created": "User invited",
  "user.unlocked": "User unlocked",
  "user.sessions_revoked": "Signed out everywhere",
  "user.reset_link_sent": "Reset link sent",
  "user.password_reset_requested": "Reset link asked for",
  "user.password_set": "Password set from invite",
  "user.password_reset": "Password reset",
  "user.password_changed": "Password changed",
  "user.two_factor_enabled": "Two-factor turned on",
  "user.two_factor_disabled": "Two-factor turned off",
  "user.two_factor_reset": "Two-factor reset",
  "user.two_factor_recovery_codes_regenerated": "New recovery codes",
  "user.two_factor_setup_started": "Two-factor set-up started",
  "flag.changed": "Feature flag switched",
  "settings.updated": "Settings saved",
  "lead.note_added": "Lead note added",
  "page.blocks_saved": "Page blocks saved",
  "page.scheduled_publish_cancelled": "Scheduled publish cancelled",
  "consent_text.created": "Consent text drafted",
  "consent_text.published": "Consent text published",
};

/** "project.published" → "Project published"; known actions use their own words. */
export function actionWords(action: string): string {
  const exact = ACTION_WORDS[action];
  if (exact) return exact;
  const dot = action.indexOf(".");
  if (dot < 0) return sentence(action.replaceAll("_", " "));
  const thing = action.slice(0, dot).replaceAll("_", " ");
  const verb = action.slice(dot + 1);
  return sentence(`${thing} ${VERBS[verb] ?? verb.replaceAll("_", " ")}`);
}

function sentence(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** How a stored value reads in a before/after line. */
export function auditValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "(none)";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "string" || typeof value === "number") return String(value);
  const text = JSON.stringify(value);
  // PERF: a long list (e.g. a reorder of 60 ids) would make one row as tall as the screen.
  return text.length > 200 ? `${text.slice(0, 199)}…` : text;
}

export interface AuditLines {
  before: string[];
  after: string[];
  /** Facts about the event that aren't a before/after pair (an export's filters, a count). */
  info: string[];
}

/** The before, after and other lines of an entry's `changes`, in the order they were written. */
export function auditLines(changes: Record<string, unknown>): AuditLines {
  const lines: AuditLines = { before: [], after: [], info: [] };
  for (const [field, value] of Object.entries(changes)) {
    const name = field.replaceAll("_", " ");
    if (Array.isArray(value) && value.length === 2) {
      lines.before.push(`${name}: ${auditValue(value[0])}`);
      lines.after.push(`${name}: ${auditValue(value[1])}`);
    } else {
      lines.info.push(`${sentence(name)}: ${auditValue(value)}`);
    }
  }
  return lines;
}

/**
 * The action filters the audit log offers, each one query the API can answer on the server
 * (`action_prefix` or an exact `action`), so the count and the pages are honest.
 * WHY not the board's six kinds as filters: "Publish" (*.published) and "Export" (*.exported)
 * are suffixes, which the API's prefix filter can't express; the kind still shows on every row.
 */
export const AUDIT_ACTION_FILTERS = {
  signins: { label: "Sign-ins", query: { action_prefix: "auth." } },
  accounts: { label: "Accounts", query: { action_prefix: "user." } },
  settings: { label: "Settings", query: { action_prefix: "settings." } },
  flags: { label: "Feature flags", query: { action_prefix: "flag." } },
  consent: { label: "Consent texts", query: { action_prefix: "consent_text." } },
  leads: { label: "Leads", query: { action_prefix: "lead." } },
  exports: { label: "Exports", query: { action: "lead.exported" } },
  erasures: { label: "Erasures", query: { action: "lead.erased" } },
  projects: { label: "Projects", query: { action_prefix: "project." } },
  pages: { label: "Pages", query: { action_prefix: "page." } },
} as const satisfies Record<
  string,
  { label: string; query: { action_prefix: string } | { action: string } }
>;

export type AuditActionFilter = keyof typeof AUDIT_ACTION_FILTERS;

/** The API query for an action filter (nothing for "all"). */
export function actionQuery(filter: AuditActionFilter | ""): {
  action_prefix?: string;
  action?: string;
} {
  return filter ? { ...AUDIT_ACTION_FILTERS[filter].query } : {};
}
