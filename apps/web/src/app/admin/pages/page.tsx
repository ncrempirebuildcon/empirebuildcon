/**
 * /admin/pages: every CMS page (home, about, contact, legal, landing and other pages) with its
 * kind, publishing state, menu place and schedule. Session checked on the server; the list is
 * loaded in the browser (ARCHITECTURE.md §5). Needs `content.read`; the API checks it again.
 */
import type { Metadata } from "next";
import { Suspense } from "react";
import { requireSessionUser } from "@/lib/session";
import { LoadingPanel } from "@/components/admin/states";
import { AdminShell } from "../AdminShell";
import { PagesList } from "./PagesList";

export const metadata: Metadata = { title: "Pages" };
export const dynamic = "force-dynamic";

export default async function PagesPage() {
  const me = await requireSessionUser();
  return (
    <AdminShell me={me} section="pages" heading="Pages">
      {/* WHY Suspense: the filters live in the address (useSearchParams). */}
      <Suspense fallback={<LoadingPanel label="Loading pages…" rows={6} />}>
        <PagesList />
      </Suspense>
    </AdminShell>
  );
}
