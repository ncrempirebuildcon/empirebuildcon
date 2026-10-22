/**
 * /admin/projects/[id]: the project editor. Session checked on the server; the project is loaded
 * and edited in the browser (ARCHITECTURE.md §5: CMS pages are client-rendered, never cached).
 */
import type { Metadata } from "next";
import { Suspense } from "react";
import { requireSessionUser } from "@/lib/session";
import { PROJECTS_PATH } from "@/lib/routes";
import { LoadingPanel } from "@/components/admin/states";
import { AdminShell } from "../../AdminShell";
import { ProjectEditor } from "./ProjectEditor";

export const metadata: Metadata = { title: "Edit project" };
export const dynamic = "force-dynamic";

export default async function ProjectEditorPage({ params }: { params: Promise<{ id: string }> }) {
  const me = await requireSessionUser();
  const { id } = await params;
  return (
    <AdminShell
      me={me}
      section="projects"
      heading="Project"
      breadcrumb={{ href: PROJECTS_PATH, label: "Projects" }}
    >
      {/* WHY Suspense: the editor reads ?tab= with useSearchParams(). */}
      <Suspense fallback={<LoadingPanel label="Loading the project…" rows={8} />}>
        <ProjectEditor id={id} />
      </Suspense>
    </AdminShell>
  );
}
