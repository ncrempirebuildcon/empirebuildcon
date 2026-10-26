/**
 * Words for one staff account on the Users screen (board NoirCmsUsers): the note under the
 * status chip and the two-factor column.
 */
import type { Schema } from "@/lib/api";
import { formatDate, formatDateTime, formatTimeOfDay } from "@/lib/dates";
import type { AccountStatus } from "@/lib/users";

export type StaffUser = Schema<"User">;

const TWO_FACTOR_ROLES = new Set(["super_admin", "admin"]);

/** The line under the status chip ("5 failed sign-ins · unlocks at 21:58"). */
export function statusNote(user: StaffUser, status: AccountStatus): string | null {
  if (status === "locked" && user.locked_until) {
    return `Too many failed sign-ins · unlocks at ${formatTimeOfDay(user.locked_until)}`;
  }
  if (status === "invited") {
    return user.invite_sent_at
      ? `Invite sent ${formatDate(user.invite_sent_at)} · not used yet`
      : "Hasn't set a password yet";
  }
  if (status === "deactivated") return "Can't sign in";
  return null;
}

/** The two-factor column: on, off, or not asked of this role. */
export function twoFactorText(user: StaffUser): string {
  if (!TWO_FACTOR_ROLES.has(user.role)) return "Not asked of this role";
  if (user.two_factor_enabled) return "On";
  return "Off";
}

/** When the account was made, for the panel ("Added 19 Oct 2026, 7:02 pm"). */
export function addedText(user: StaffUser): string {
  return `Added ${formatDateTime(user.created_at)}`;
}
