/**
 * /admin/posts/new: write a new blog post; the first save creates it and opens its editor.
 * Needs `content.write`; the API checks it again.
 */
import type { Metadata } from "next";
import { requireSessionUser } from "@/lib/session";
import { POSTS_PATH } from "@/lib/routes";
import { AdminShell } from "../../AdminShell";
import { PostEditor } from "../[id]/PostEditor";

export const metadata: Metadata = { title: "New post" };
export const dynamic = "force-dynamic";

export default async function NewPostPage() {
  const me = await requireSessionUser();
  return (
    <AdminShell
      me={me}
      section="content"
      heading="New post"
      breadcrumb={{ href: POSTS_PATH, label: "Blog posts" }}
    >
      <PostEditor id={null} />
    </AdminShell>
  );
}
