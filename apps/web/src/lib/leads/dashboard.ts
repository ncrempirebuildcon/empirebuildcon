/**
 * Reading the dashboard answer (`GET /admin/dashboard`, schema `Dashboard`): the unread count for
 * the Leads badge, and the action words each count tile shows ("Open new leads →").
 *
 * The API owns the counts, their labels and their links (`DashboardCount.link`, a CMS path with
 * filters); this file only adds the words for the tile's call to action, keyed by `key`.
 */
import type { Schema } from "../api";

type Dashboard = Schema<"Dashboard">;

/** Count keys the API sends (DashboardCount.key). Unknown keys still show, with a plain "Open". */
export const COUNT_KEYS = {
  leadsNew: "leads.new",
  leadsUnread: "leads.unread",
  leadsUnassigned: "leads.unassigned",
  visitsToday: "visits.today",
  visitsWeek: "visits.week",
  projectsPublished: "projects.published",
  projectsDraft: "projects.draft",
  projectsBlocked: "projects.blocked",
} as const;

const ACTIONS: Record<string, string> = {
  [COUNT_KEYS.leadsNew]: "Open new leads",
  [COUNT_KEYS.leadsUnread]: "Open unread leads",
  [COUNT_KEYS.leadsUnassigned]: "Assign owners",
  [COUNT_KEYS.visitsToday]: "See today",
  [COUNT_KEYS.visitsWeek]: "See calendar",
  [COUNT_KEYS.projectsPublished]: "Manage projects",
  [COUNT_KEYS.projectsDraft]: "Finish drafts",
  [COUNT_KEYS.projectsBlocked]: "See what's missing",
};

/** The call to action under a count tile. */
export function countAction(key: string): string {
  return ACTIONS[key] ?? "Open";
}

/** The unread-leads count for the menu badge, or null when the dashboard doesn't send it. */
export function unreadLeadCount(dashboard: Dashboard): number | null {
  const count = dashboard.counts?.find((c) => c.key === COUNT_KEYS.leadsUnread);
  return count ? count.count : null;
}
