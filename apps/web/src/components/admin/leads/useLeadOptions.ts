"use client";
/**
 * Choices the lead screens offer in their lists: the projects (filter, manual lead, lead detail)
 * and the staff a lead or a site visit can be given to.
 *
 * WHY a catch on the staff list: it only fills a dropdown; without it the screen still works
 * (owner shown as text), so a failure there must not replace the whole screen with an error.
 *
 * Projects come from `GET /admin/projects` (every role has `projects.read`); archived projects
 * stay listed because older leads keep their project (ARCHITECTURE §6 "Deletion").
 */
import type { SelectOption } from "@empire/ui";
import { api, call } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/labels";
import { useLoad } from "@/components/admin/useLoad";

/** Projects as select options, sample and archived ones marked so. */
export function useProjectOptions(): SelectOption[] {
  const projects = useLoad("lead-projects", () =>
    call(api.GET("/api/v1/admin/projects", { params: { query: { per_page: 100 } } })),
  );
  return (projects.data?.items ?? []).map((project) => ({
    value: project.id,
    label:
      project.name +
      (project.publish_state === "archived" ? " (archived)" : "") +
      (project.is_sample ? " · SAMPLE" : ""),
  }));
}

/**
 * Staff a lead or a site visit can be given to (`GET /admin/lead-owners`), as select options
 * "Name · Role". Loaded only when `enabled` (the role can assign, filter by owner or set who
 * handles a visit); otherwise, or if the list can't be loaded, it is empty and the screens
 * simply don't offer the choice. The API checks every assignment again.
 */
export function useStaffOptions(enabled: boolean): SelectOption[] {
  const owners = useLoad(`lead-owners:${enabled}`, () =>
    enabled ? call(api.GET("/api/v1/admin/lead-owners")).catch(() => []) : Promise.resolve([]),
  );
  return (owners.data ?? []).map((owner) => ({
    value: owner.id,
    label: `${owner.name} · ${ROLE_LABELS[owner.role] ?? owner.role}`,
  }));
}
