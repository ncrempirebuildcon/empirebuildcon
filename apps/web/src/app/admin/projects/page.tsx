/**
 * /admin/projects: the projects list. Session checked on the server, list loaded in the browser
 * (ARCHITECTURE.md §5: CMS pages are client-rendered and never cached).
 */
import type { Metadata } from "next";
import { Suspense } from "react";
import { requireSessionUser } from "@/lib/session";
import { LoadingPanel } from "@/components/admin/states";
import { AdminShell } from "../AdminShell";
import { ProjectsList } from "./ProjectsList";

export const metadata: Metadata = { title: "Projects" };
export const dynamic = "force-dynamic";

export default async function ProjectsPage() {
  const me = await requireSessionUser();
  return (
    <AdminShell me={me} section="projects" heading="Projects">
      {/* WHY Suspense: ProjectsList reads the filters with useSearchParams(). */}
      <Suspense fallback={<LoadingPanel label="Loading projects…" />}>
        <ProjectsList />
      </Suspense>
    </AdminShell>
  );
}
