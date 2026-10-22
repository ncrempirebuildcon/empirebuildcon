"use client";
/**
 * Shared types for the project editor's tabs, and the helper that tells the editor a tab has
 * unsaved changes (for the leave warning).
 */
import { useEffect } from "react";
import type { Schema } from "@/lib/api";
import type { ProjectAdmin } from "./projectForm";

export type Tower = Schema<"Tower">;
export type Configuration = Schema<"Configuration">;
export type Specification = Schema<"Specification">;
export type LocationAdvantage = Schema<"LocationAdvantage">;
export type ConstructionUpdate = Schema<"ConstructionUpdate">;
export type PaymentPlan = Schema<"PaymentPlan">;
export type Amenity = Schema<"Amenity">;

/** Props every child-list tab gets from the editor. */
export interface ChildTabProps {
  project: ProjectAdmin;
  /** False for roles without `projects.write`: the tab is read-only. */
  canWrite: boolean;
  /** Re-reads the project after a change (lists, order and publish blockers). */
  onChanged: () => Promise<unknown>;
  /** Tells the editor whether this tab has unsaved changes. */
  reportDirty: (key: string, dirty: boolean) => void;
}

/** Reports `dirty` for `key` whenever it changes, and clears it when the tab goes away. */
export function useReportDirty(
  key: string,
  dirty: boolean,
  reportDirty: (key: string, dirty: boolean) => void,
) {
  useEffect(() => {
    reportDirty(key, dirty);
  }, [key, dirty, reportDirty]);
  useEffect(() => () => reportDirty(key, false), [key, reportDirty]);
}

/** "" ↔ null for optional text inputs. */
export const orNull = (value: string) => (value.trim() === "" ? null : value.trim());
