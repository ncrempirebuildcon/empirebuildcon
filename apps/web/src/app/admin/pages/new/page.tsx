/**
 * /admin/pages/new: start a page (title, web address, kind); the page editor opens next.
 * Needs `content.write`; the API checks it again.
 */
import type { Metadata } from "next";
import { requireSessionUser } from "@/lib/session";
import { PAGES_PATH } from "@/lib/routes";
import { AdminShell } from "../../AdminShell";
import { NewPageForm } from "./NewPageForm";

export const metadata: Metadata = { title: "New page" };
export const dynamic = "force-dynamic";

export default async function NewPagePage() {
  const me = await requireSessionUser();
  return (
    <AdminShell
      me={me}
      section="pages"
      heading="New page"
      breadcrumb={{ href: PAGES_PATH, label: "Pages" }}
    >
      <NewPageForm />
    </AdminShell>
  );
}
