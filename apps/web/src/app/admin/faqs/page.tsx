/**
 * /admin/faqs: FAQs in the "Offers & blog" section (board NoirCmsContent). Session checked on
 * the server; the screen is loaded in the browser (ARCHITECTURE.md §5). Needs `content.read`; the
 * API checks it again.
 */
import type { Metadata } from "next";
import { Suspense } from "react";
import { requireSessionUser } from "@/lib/session";
import { LoadingPanel } from "@/components/admin/states";
import { AdminShell } from "../AdminShell";
import { FaqsScreen } from "./FaqsScreen";

export const metadata: Metadata = { title: "FAQs" };
export const dynamic = "force-dynamic";

export default async function FaqsPage() {
  const me = await requireSessionUser();
  return (
    <AdminShell me={me} section="content" heading="Offers & blog">
      {/* WHY Suspense: the screen keeps its filters or selection in the address. */}
      <Suspense fallback={<LoadingPanel label="Loading FAQs…" rows={6} />}>
        <FaqsScreen />
      </Suspense>
    </AdminShell>
  );
}
