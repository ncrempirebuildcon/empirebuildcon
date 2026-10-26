/**
 * /admin/posts: blog and news posts (board NoirCmsContent, "Blog posts"). Needs `content.read`;
 * the API checks it again.
 */
import type { Metadata } from "next";
import { Suspense } from "react";
import { requireSessionUser } from "@/lib/session";
import { LoadingPanel } from "@/components/admin/states";
import { AdminShell } from "../AdminShell";
import { PostsList } from "./PostsList";

export const metadata: Metadata = { title: "Blog posts" };
export const dynamic = "force-dynamic";

export default async function PostsPage() {
  const me = await requireSessionUser();
  return (
    <AdminShell me={me} section="content" heading="Offers & blog">
      {/* WHY Suspense: the filters live in the address (useSearchParams). */}
      <Suspense fallback={<LoadingPanel label="Loading posts…" rows={6} />}>
        <PostsList />
      </Suspense>
    </AdminShell>
  );
}
