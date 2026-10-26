/**
 * /admin/pages/[id]: the page editor (board NoirCmsPage): blocks, settings and SEO. Session
 * checked on the server; the page is loaded and edited in the browser (ARCHITECTURE.md §5).
 */
import type { Metadata } from "next";
import { Suspense } from "react";
import { requireSessionUser } from "@/lib/session";
import { PAGES_PATH } from "@/lib/routes";
import { LoadingPanel } from "@/components/admin/states";
import { AdminShell } from "../../AdminShell";
import { PageEditor } from "./PageEditor";

export const metadata: Metadata = { title: "Edit page" };
export const dynamic = "force-dynamic";

export default async function PageEditorPage({ params }: { params: Promise<{ id: string }> }) {
  const me = await requireSessionUser();
  const { id } = await params;
  return (
    <AdminShell
      me={me}
      section="pages"
      heading="Page"
      breadcrumb={{ href: PAGES_PATH, label: "Pages" }}
    >
      {/* WHY Suspense: the editor reads ?tab= with useSearchParams(). */}
      <Suspense fallback={<LoadingPanel label="Loading the page…" rows={8} />}>
        <PageEditor id={id} />
      </Suspense>
    </AdminShell>
  );
}
