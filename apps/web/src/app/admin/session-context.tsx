"use client";
/**
 * The signed-in staff member and their permissions, shared with every CMS screen inside
 * AdminShell, plus a way for a screen to set the page heading in the shell's top bar, and the
 * dashboard counts the shell loads once per page (the Leads badge and the dashboard read them).
 *
 * SECURITY: `can()` only decides what to show. The API checks the same permission on every call
 * (ARCHITECTURE.md §11); hiding a button is never the protection.
 */
import { createContext, useContext, useEffect } from "react";
import type { Schema, SessionUser } from "@/lib/api";

/** Permission keys from the matrix in handbook/ARCHITECTURE.md §11 used by the CMS screens. */
export type Permission =
  | "dashboard.view"
  | "projects.read"
  | "projects.write"
  | "projects.publish"
  | "projects.delete"
  | "leads.read"
  | "leads.read_all"
  | "leads.update"
  | "leads.assign"
  | "leads.export"
  | "leads.report"
  | "leads.erase"
  | "site_visits.manage"
  | (string & {});

/** The dashboard as the shell loaded it (`GET /admin/dashboard`). */
export interface DashboardState {
  data?: Schema<"Dashboard">;
  error?: unknown;
  loading: boolean;
  /** Try again after an error (shows the loading state). */
  reload: () => void;
  /** Fetch again quietly, e.g. after a lead was opened, so the unread badge goes down. */
  refresh: () => Promise<void>;
}

export interface AdminSession {
  me: SessionUser;
  can: (permission: Permission) => boolean;
  /** Replace the heading in the shell's top bar (e.g. with the project's name once loaded). */
  setHeading: (heading: string) => void;
  /** Tell the shell the screen has unsaved changes, so Sign out asks first. */
  setUnsaved: (unsaved: boolean) => void;
  /** The dashboard counts, latest leads and tasks; `null` when the role has no dashboard. */
  dashboard: DashboardState | null;
}

export const AdminSessionContext = createContext<AdminSession | null>(null);

export function useAdminSession(): AdminSession {
  const session = useContext(AdminSessionContext);
  if (!session) throw new Error("useAdminSession must be used inside AdminShell");
  return session;
}

/** Sets the top-bar heading while the calling screen is shown. */
export function useAdminHeading(heading: string | null) {
  const { setHeading } = useAdminSession();
  useEffect(() => {
    if (heading) setHeading(heading);
  }, [heading, setHeading]);
}
