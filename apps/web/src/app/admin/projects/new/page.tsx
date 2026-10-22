/**
 * /admin/projects/new: the short create form (name, construction status, optional city).
 * Everything else is filled in on the editor it opens next.
 */
import type { Metadata } from "next";
import { requireSessionUser } from "@/lib/session";
import { PROJECTS_PATH } from "@/lib/routes";
import { AdminShell } from "../../AdminShell";
import { NewProjectForm } from "./NewProjectForm";

export const metadata: Metadata = { title: "New project" };
export const dynamic = "force-dynamic";

export default async function NewProjectPage() {
  const me = await requireSessionUser();
  return (
    <AdminShell
      me={me}
      section="projects"
      heading="New project"
      breadcrumb={{ href: PROJECTS_PATH, label: "Projects" }}
    >
      <NewProjectForm />
    </AdminShell>
  );
}
