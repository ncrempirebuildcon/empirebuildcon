/**
 * Staff accounts for the Users & roles screen (board NoirCmsUsers): role names and order, the
 * board's one-line summary of each role, how a user's status reads, and the groups of the
 * permission table.
 *
 * SECURITY: which role has which permission comes only from the API (`GET /admin/roles`, the
 * matrix in apps/api users/roles.py, ARCHITECTURE §11). This file only decides how it is shown.
 */
import type { Schema } from "./api";

export type RoleKey = Schema<"User">["role"];

/** Roles in the board's order, most rights first. */
export const ROLE_ORDER: readonly RoleKey[] = [
  "super_admin",
  "admin",
  "sales",
  "marketing",
  "content_editor",
];

/**
 * Roles offered when inviting (board: Sales, Marketing, Content editor, Admin). WHY no
 * super-admin: a second super-admin is a deliberate promotion, made with "Change role" and its
 * confirmation, not a choice in the invite form.
 */
export const INVITE_ROLES: readonly RoleKey[] = ["sales", "marketing", "content_editor", "admin"];

/** What each role is for, in the board's words (the role picker's status line). */
export const ROLE_SUMMARIES: Record<RoleKey, string> = {
  super_admin:
    "Everything, including users and roles and erasing a buyer's personal data on request. One account at launch: the owner.",
  admin:
    "Runs the CMS day to day: projects, leads, content, offers, settings, flags and the audit log. Can't manage users or erase data.",
  sales:
    "Works their own leads and the site-visit calendar. Sees projects read-only and the UTM report as counts only.",
  marketing:
    "Offers, tracking IDs, SEO, pages, posts and media. Sees lead counts by source, never lead details.",
  content_editor:
    "Projects, configurations, pages, posts, FAQs, media and SEO. Can't publish projects or see leads.",
};

/**
 * The permission table's groups (board NoirCmsUsers), by the permission's prefix: a fallback for
 * a row the API sends without a `group` (GET /admin/permissions names one for every row today).
 */
const GROUPS: ReadonlyArray<{ name: string; prefixes: readonly string[] }> = [
  { name: "Dashboard & projects", prefixes: ["dashboard.", "projects."] },
  { name: "Media", prefixes: ["media."] },
  { name: "Leads & site visits", prefixes: ["leads.", "site_visits."] },
  { name: "Content & SEO", prefixes: ["content.", "legal.", "offers.", "seo."] },
  {
    name: "Settings & system",
    prefixes: ["settings.", "marketing.", "flags.", "integrations.", "audit.", "users."],
  },
];

/** The table group of a permission key; a key no group names goes under "Other". */
export function permissionGroup(key: string): string {
  return GROUPS.find((group) => group.prefixes.some((p) => key.startsWith(p)))?.name ?? "Other";
}

/**
 * Permission rows grouped for the table: by the API's `group` when it sends one (else by
 * prefix), groups in the order they first appear, rows in the API's order inside each group.
 */
export function groupPermissions<T extends { key: string; group?: string }>(
  permissions: readonly T[],
): Array<{ name: string; rows: T[] }> {
  const groups = new Map<string, T[]>();
  for (const row of permissions) {
    const name = row.group || permissionGroup(row.key);
    groups.set(name, [...(groups.get(name) ?? []), row]);
  }
  return [...groups].map(([name, rows]) => ({ name, rows }));
}

/** "SO" for "Sales One", "AD" for "admin"; at most two letters, for the avatar circle. */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return (words[0] ?? "").slice(0, 2).toUpperCase();
  return words
    .slice(0, 2)
    .map((word) => word.charAt(0))
    .join("")
    .toUpperCase();
}

/** "1 user", "No users", "3 users" (the role picker's count). */
export function userCountText(count: number): string {
  if (count === 0) return "No users";
  return count === 1 ? "1 user" : `${count} users`;
}

/** An account's state, as the board's status chip shows it. */
export type AccountStatus = "active" | "invited" | "locked" | "deactivated";

export const ACCOUNT_STATUS: Record<AccountStatus, string> = {
  active: "Active",
  invited: "Invited",
  locked: "Locked",
  deactivated: "Deactivated",
};

interface StatusFields {
  is_active: boolean;
  locked_until?: string | null;
  last_login_at?: string | null;
  /** Sent by the API from Phase 4 part 5; preferred when present. */
  status?: string | null;
}

/**
 * The account's status: the API's own `status` when it sends one; otherwise worked out from the
 * fields (deactivated, then locked until a time still ahead, then never signed in = invited).
 */
export function accountStatus(user: StatusFields, now: number = Date.now()): AccountStatus {
  if (user.status && Object.hasOwn(ACCOUNT_STATUS, user.status)) {
    return user.status as AccountStatus;
  }
  if (!user.is_active) return "deactivated";
  if (user.locked_until && Date.parse(user.locked_until) > now) return "locked";
  if (!user.last_login_at) return "invited";
  return "active";
}
