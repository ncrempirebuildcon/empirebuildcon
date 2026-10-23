/**
 * /admin/media: the media library, every photo, video and document uploaded to the CMS.
 * Session checked on the server; the library is loaded in the browser (ARCHITECTURE.md §5).
 * The screen needs `media.upload` (the menu item is shown only with it); the API checks it again.
 */
import type { Metadata } from "next";
import { Suspense } from "react";
import { requireSessionUser } from "@/lib/session";
import { LoadingPanel } from "@/components/admin/states";
import { AdminShell } from "../AdminShell";
import { MediaLibrary } from "./MediaLibrary";

export const metadata: Metadata = { title: "Media" };
export const dynamic = "force-dynamic";

export default async function MediaPage() {
  const me = await requireSessionUser();
  return (
    <AdminShell me={me} section="media" heading="Media">
      {/* WHY Suspense: the filters live in the address (useSearchParams). */}
      <Suspense fallback={<LoadingPanel label="Loading the media library…" rows={6} />}>
        <MediaLibrary />
      </Suspense>
    </AdminShell>
  );
}
