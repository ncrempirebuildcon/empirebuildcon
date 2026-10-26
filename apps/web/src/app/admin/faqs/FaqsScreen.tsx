"use client";
/**
 * /admin/faqs (board NoirCmsContent, "FAQs"): the site-wide FAQs, or one project's, chosen with
 * the "Which FAQs" filter. The choice lives in the address (`?project=<id>`), so a link can open
 * a project's FAQs directly. Each group is ordered and edited by FaqManager; the project editor's
 * FAQs tab shows the same group for its project.
 */
import { useCallback, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { Select } from "@empire/ui";
import { api, call } from "@/lib/api";
import { FAQS_PATH } from "@/lib/routes";
import { ContentHeader } from "@/components/admin/content/ContentNav";
import { FaqManager } from "@/components/admin/content/FaqManager";
import { useLoad } from "@/components/admin/useLoad";
import { useDirtyParts, useUnsavedChanges } from "@/components/admin/useUnsavedChanges";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function FaqsScreen() {
  const params = useSearchParams();
  const raw = params.get("project") ?? "";
  const projectId = UUID_RE.test(raw) ? raw : null;
  const projects = useLoad("faq-projects", () =>
    call(api.GET("/api/v1/admin/projects", { params: { query: { per_page: 100 } } })),
  );
  const options = useMemo(
    () =>
      (projects.data?.items ?? []).map((project) => ({
        value: project.id,
        label: project.is_sample ? `${project.name} (SAMPLE)` : project.name,
      })),
    [projects.data],
  );
  const parts = useDirtyParts();
  const { report } = parts;
  // WHY useCallback: FaqManager reports through an effect keyed on this function.
  const onDirtyChange = useCallback((dirty: boolean) => report("faq-form", dirty), [report]);
  const { dialog, leave } = useUnsavedChanges(parts.dirty);
  const projectName = options.find((option) => option.value === projectId)?.label;

  return (
    <>
      <ContentHeader
        current="faqs"
        description="FAQs show on their project's page (and in its FAQ structured data). Site-wide FAQs show on the Contact page. Use Move up and Move down to change the order."
      />
      <Select
        id="faqs-group"
        label="Which FAQs"
        value={projectId ?? ""}
        placeholder="Site-wide (Contact page)"
        options={options}
        onChange={(event) => {
          const next = event.target.value;
          leave(next ? `${FAQS_PATH}?project=${next}` : FAQS_PATH, { replace: true });
        }}
        className="max-w-md"
        hint={projects.loading ? "Loading projects…" : undefined}
      />
      <FaqManager
        key={projectId ?? "site"}
        projectId={projectId}
        title={projectId ? `${projectName ?? "Project"} · FAQs` : "Site-wide FAQs"}
        description={projectId ? "Shown on the project page." : "Shown on the Contact page."}
        onDirtyChange={onDirtyChange}
      />
      {dialog}
    </>
  );
}
