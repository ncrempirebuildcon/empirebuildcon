/**
 * /admin/posts/[id]: one blog post's editor (title, address, excerpt, body with preview, cover,
 * category, tags, SEO, publish). Loaded and edited in the browser (ARCHITECTURE.md §5).
 */
import type { Metadata } from "next";
import { requireSessionUser } from "@/lib/session";
import { POSTS_PATH } from "@/lib/routes";
import { AdminShell } from "../../AdminShell";
import { PostEditor } from "./PostEditor";

export const metadata: Metadata = { title: "Edit post" };
export const dynamic = "force-dynamic";

export default async function PostEditorPage({ params }: { params: Promise<{ id: string }> }) {
  const me = await requireSessionUser();
  const { id } = await params;
  return (
    <AdminShell
      me={me}
      section="content"
      heading="Post"
      breadcrumb={{ href: POSTS_PATH, label: "Blog posts" }}
    >
      <PostEditor id={id} />
    </AdminShell>
  );
}
