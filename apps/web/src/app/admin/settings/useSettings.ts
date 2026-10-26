"use client";
/**
 * Loads `GET /admin/settings` (SettingsOverview: every group's values, each group's permission
 * and whether this viewer can edit it, the round-robin preview and the integrations status) once
 * for the Settings screen, and saves groups with `PATCH /admin/settings/{group}`: one request
 * per changed group, in order; the first refusal stops the rest and is thrown, so the form can
 * show the API's messages at its fields. Each answer (the group's full values) replaces that
 * group in memory; after a lead-routing save the overview is read again quietly, so the
 * round-robin preview ("Gets the next lead") matches what was saved.
 */
import { useCallback, useMemo } from "react";
import { api, call, type Schema } from "@/lib/api";
import { useLoad } from "@/components/admin/useLoad";
import type { GroupPatches, GroupValues } from "./fieldValues";

export type SettingsAnswer = Schema<"SettingsOverview">;
export type GroupMeta = Schema<"SettingsGroupMeta">;
export type GroupKey = GroupMeta["key"];

export const GROUP_KEYS: readonly GroupKey[] = [
  "company",
  "contacts",
  "social",
  "tracking",
  "lead_routing",
  "seo_defaults",
  "regulator",
  "email",
  "privacy",
];

function isGroupKey(value: string): value is GroupKey {
  return (GROUP_KEYS as readonly string[]).includes(value);
}

export interface SettingsState {
  data?: SettingsAnswer;
  error?: unknown;
  reload: () => void;
  /** Every group's stored values, by group key. */
  groups: GroupValues;
  /** Who may edit each group, by group key. */
  meta: Partial<Record<GroupKey, GroupMeta>>;
  /** Saves the changed groups; throws the first refusal. */
  save: (patches: GroupPatches) => Promise<void>;
}

export function useSettings(): SettingsState {
  const load = useLoad("settings", () => call(api.GET("/api/v1/admin/settings")));
  const { data, replace, refresh } = load;

  const groups = useMemo<GroupValues>(() => {
    if (!data) return {};
    return Object.fromEntries(
      GROUP_KEYS.map((key) => [key, data[key] as unknown as Record<string, unknown>]),
    );
  }, [data]);
  const meta = useMemo(
    () => Object.fromEntries((data?.groups ?? []).map((m) => [m.key, m])),
    [data],
  ) as Partial<Record<GroupKey, GroupMeta>>;

  const save = useCallback(
    async (patches: GroupPatches) => {
      let current = data;
      for (const [group, patch] of Object.entries(patches)) {
        if (!isGroupKey(group)) continue;
        const saved = await call(
          api.PATCH("/api/v1/admin/settings/{group}", {
            params: { path: { group } },
            body: patch,
          }),
        );
        if (current) {
          current = { ...current, [group]: saved } as SettingsAnswer;
          replace(current);
        }
        // The round-robin preview depends on the saved routing: read the overview again.
        if (group === "lead_routing") await refresh().catch(() => undefined);
      }
    },
    [data, replace, refresh],
  );

  return { data, error: load.error, reload: load.reload, groups, meta, save };
}
