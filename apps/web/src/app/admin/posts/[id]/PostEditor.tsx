"use client";
/**
 * The blog post editor (/admin/posts/new and /admin/posts/[id]): title, web address, excerpt,
 * the body with a live preview (FormattedTextEditor), cover image, category, tags, SEO, and
 * publishing (spec Phase 4 part 4 §3).
 *
 * How saving works:
 *   1. A new post is created by its first "Save draft" (POST), then the editor's own address
 *      opens (`/admin/posts/<id>`). The web address is made from the title unless typed.
 *   2. An existing post saves the changed fields only (PATCH, postForm.ts). Field errors from
 *      the API appear next to their fields, and a summary links to the tab that has them.
 *   3. Leaving with unsaved changes asks first; Publish waits for a save.
 *
 * Permissions: `content.write` edits, `content.publish` publishes and unpublishes, `seo.manage`
 * edits the SEO tab, `media.upload` uploads a cover. The API checks them all again.
 */
import Link from "next/link";
import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { Alert, FormattedTextEditor, TabPanel, Tabs, TextField, Textarea } from "@empire/ui";
import { api, call } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { POST_CATEGORIES } from "@/lib/content/posts";
import { slugify } from "@/lib/content/slug";
import { fieldErrors, problemMessage, toProblem, type FieldErrors } from "@/lib/problems";
import { POSTS_PATH, postPath } from "@/lib/routes";
import { MediaField } from "@/components/admin/media/MediaField";
import { EditorStatusBar, SampleNote } from "@/components/admin/content/EditorStatusBar";
import { SaveErrorSummary } from "@/components/admin/content/SaveErrorSummary";
import { SeoFields } from "@/components/admin/content/SeoFields";
import { usePublishActions } from "@/components/admin/content/usePublishActions";
import { ErrorPanel, LoadingPanel, Panel } from "@/components/admin/states";
import { useLoad } from "@/components/admin/useLoad";
import { useDirtyParts, useUnsavedChanges } from "@/components/admin/useUnsavedChanges";
import { useAdminHeading, useAdminSession } from "../../session-context";
import { PostPublishing } from "./PostPublishing";
import {
  EMPTY_POST,
  checkForm,
  sameForm,
  toCreate,
  toForm,
  toUpdate,
  type Post,
  type PostForm,
} from "./postForm";

const TABS = [
  { id: "post", label: "Post" },
  { id: "seo", label: "SEO" },
] as const;
type TabId = (typeof TABS)[number]["id"];

const FIELD_LABELS: Record<string, string> = {
  title: "Title",
  slug: "Web address",
  excerpt: "Excerpt",
  body: "Post",
  cover_media_id: "Cover image",
  category: "Category",
  tags: "Tags",
  "seo.title": "Search title",
  "seo.description": "Search description",
  "seo.canonical_path": "Canonical path",
  "seo.og_image_id": "Share image",
};

export function PostEditor({ id }: { id: string | null }) {
  if (id === null) return <PostBody post={null} />;
  return <ExistingPost id={id} />;
}

function ExistingPost({ id }: { id: string }) {
  const post = useLoad(`post:${id}`, () =>
    call(api.GET("/api/v1/admin/posts/{id}", { params: { path: { id } } })),
  );
  useAdminHeading(post.data?.title ?? null);
  if (post.error && !post.data) {
    if (toProblem(post.error).status === 404) {
      return (
        <Alert tone="error" title="This post doesn't exist or was deleted.">
          <Link href={POSTS_PATH} className="font-bold underline">
            Back to blog posts
          </Link>
        </Alert>
      );
    }
    return (
      <ErrorPanel
        message={problemMessage(post.error, "Couldn't load the post.")}
        onRetry={post.reload}
      />
    );
  }
  if (!post.data) return <LoadingPanel label="Loading the post…" rows={8} />;
  return <PostBody post={post.data} replace={post.replace} refresh={post.refresh} />;
}

function PostBody({
  post,
  replace,
  refresh,
}: {
  post: Post | null;
  replace?: (post: Post) => void;
  refresh?: () => Promise<Post>;
}) {
  const { can } = useAdminSession();
  const router = useRouter();
  const canWrite = can("content.write");
  const canPublish = can("content.publish");
  const canUpload = can("media.upload");
  const isNew = post === null;
  const [tab, setTab] = useState<TabId>("post");
  const [form, setFormState] = useState<PostForm>(() => (post ? toForm(post) : EMPTY_POST));
  const [savedForm, setSavedForm] = useState<PostForm>(() => (post ? toForm(post) : EMPTY_POST));
  const [slugEdited, setSlugEdited] = useState(!isNew);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const uploads = useDirtyParts();

  const formDirty = !sameForm(form, savedForm);
  const dirty = formDirty || uploads.dirty;
  const { dialog: leaveDialog } = useUnsavedChanges(dirty && !saving);

  const setForm = useCallback((patch: Partial<PostForm>) => {
    setFormState((current) => ({ ...current, ...patch }));
    setNotice(null);
  }, []);

  // The actions are only offered once the post exists (it has an id).
  const path = () => {
    if (!post) throw new Error("The post isn't saved yet.");
    return { params: { path: { id: post.id } } };
  };
  const actions = usePublishActions<Post>({
    noun: "post",
    title: post?.title ?? "",
    afterDelete: `${POSTS_PATH}?notice=deleted`,
    calls: {
      publish: () => call(api.POST("/api/v1/admin/posts/{id}/publish", path())),
      unpublish: () => call(api.POST("/api/v1/admin/posts/{id}/unpublish", path())),
      setState: (state) =>
        call(api.PATCH("/api/v1/admin/posts/{id}", { ...path(), body: { publish_state: state } })),
      remove: () => call(api.DELETE("/api/v1/admin/posts/{id}", path())),
    },
    onUpdated: (updated) => replace?.(updated),
    refresh: () => refresh?.() ?? Promise.resolve(),
    onNotice: (text) => {
      setSaveError(null);
      setNotice(text);
    },
    onError: (text) => {
      setNotice(null);
      setSaveError(text);
    },
  });

  async function save() {
    if (saving) return;
    setNotice(null);
    const sent = isNew && !slugEdited ? { ...form, slug: "" } : form;
    const found = checkForm(sent, isNew);
    if (Object.keys(found).length > 0) {
      setErrors(found);
      setSaveError("Some fields need attention.");
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      if (isNew) {
        const created = await call(api.POST("/api/v1/admin/posts", { body: toCreate(sent) }));
        // WHY replace: the new post's own address keeps a reload on the saved post.
        setSavedForm(toForm(created));
        router.replace(postPath(created.id));
        return;
      }
      const updated = await call(
        api.PATCH("/api/v1/admin/posts/{id}", {
          params: { path: { id: post.id } },
          body: toUpdate(sent, savedForm),
        }),
      );
      replace?.(updated);
      const saved = toForm(updated);
      setSavedForm(saved);
      setFormState(saved);
      setErrors({});
      setNotice(
        post.publish_state === "published" && updated.path !== post.path
          ? `Saved. The old address ${post.path} now redirects to ${updated.path}.`
          : "Saved.",
      );
    } catch (err) {
      setErrors(fieldErrors(err));
      setSaveError(problemMessage(err, "Couldn't save the post."));
    } finally {
      setSaving(false);
    }
  }

  const state = post?.publish_state ?? "draft";
  const shownSlug = isNew && !slugEdited ? slugify(form.title) : form.slug;
  const address = post ? post.path.replace(/[^/]+$/, "") : "/blog/";
  const errorList = Object.entries(errors);
  const tabOf = (field: string): TabId => (field.startsWith("seo.") ? "seo" : "post");

  return (
    <>
      {post?.is_sample ? <SampleNote /> : null}
      <EditorStatusBar
        isSample={post?.is_sample ?? false}
        state={state}
        stateLabel={isNew ? "New draft" : undefined}
        dirty={dirty}
        meta={
          post
            ? [
                post.path,
                post.author ? `by ${post.author.name}` : null,
                `last saved ${formatDateTime(post.updated_at)}`,
                post.published_at ? `published ${formatDateTime(post.published_at)}` : null,
              ]
                .filter(Boolean)
                .join(" · ")
            : null
        }
        save={canWrite ? { onClick: save, busy: saving, disabled: !formDirty && !isNew } : null}
        publish={
          post && canPublish
            ? {
                onClick: actions.publish,
                busy: actions.busy === "publish",
                disabled: post.publish_blockers.length > 0 || dirty,
                describedBy: "post-publish-status",
              }
            : null
        }
        unpublish={
          post && canPublish
            ? { onClick: actions.askUnpublish, busy: actions.busy === "unpublish" }
            : null
        }
      />

      {notice ? <Alert tone="success">{notice}</Alert> : null}
      {saveError ? (
        <SaveErrorSummary
          title={saveError}
          problems={errorList.map(([field, text]) => ({
            key: field,
            text: `${FIELD_LABELS[field] ?? field}: ${text}`,
            onGo: () => setTab(tabOf(field)),
          }))}
        />
      ) : null}
      {!canWrite ? (
        <Alert tone="info">
          You can view this post. Editing needs the content.write permission.
        </Alert>
      ) : null}

      <div className="flex flex-col gap-4">
        <Tabs
          label="Post sections"
          idPrefix="post"
          tabs={TABS}
          selected={tab}
          onSelect={(next) => setTab(next as TabId)}
        />
        <TabPanel idPrefix="post" tabId="post" selected={tab === "post"}>
          <fieldset
            disabled={!canWrite || saving}
            className="flex min-w-0 flex-wrap items-start gap-5"
          >
            <legend className="sr-only">Post</legend>
            <Panel id="post-main" title="Post" className="min-w-0 flex-[2_1_420px]">
              <TextField
                id="post-title"
                label="Title"
                required
                maxLength={160}
                value={form.title}
                onChange={(event) => setForm({ title: event.target.value })}
                error={errors.title}
              />
              <TextField
                id="post-slug"
                label="Web address"
                required={!isNew}
                maxLength={120}
                value={shownSlug}
                onChange={(event) => {
                  setSlugEdited(true);
                  setForm({ slug: event.target.value.trim().toLowerCase() });
                }}
                error={errors.slug}
                hint={
                  <span className="flex flex-col gap-0.5">
                    <span>
                      Shown as{" "}
                      <strong className="text-ivory">
                        empirebuildcon.com{address}
                        {shownSlug || "[web-address]"}
                      </strong>
                    </span>
                    {state === "published" ? (
                      <span>
                        This post is live: changing the address makes the old one redirect here.
                      </span>
                    ) : isNew ? (
                      <span>Made from the title until you change it.</span>
                    ) : null}
                  </span>
                }
              />
              <Textarea
                id="post-excerpt"
                label="Excerpt (optional)"
                rows={2}
                maxLength={300}
                value={form.excerpt}
                onChange={(event) => setForm({ excerpt: event.target.value })}
                error={errors.excerpt}
                hint="One or two sentences for the blog list and search results."
              />
              <FormattedTextEditor
                id="post-body"
                label="Post"
                required
                rows={14}
                limit={50000}
                value={form.body}
                onChange={(body) => setForm({ body })}
                error={errors.body}
                hint="Check every figure (tax, stamp duty, the law) against the official source and name it."
              />
            </Panel>
            <Panel id="post-details" title="Cover and filing" className="min-w-0 flex-[1_1_280px]">
              <MediaField
                id="post-cover"
                label="Cover image"
                kind="image"
                labelRequired
                value={form.cover}
                onChange={(cover) => setForm({ cover })}
                canUpload={canUpload && canWrite}
                disabled={!canWrite}
                error={errors.cover_media_id}
                hint="Shown at the top of the post and in the blog list, with its honest label."
                onBusyChange={(busy) => uploads.report("cover", busy)}
              />
              <TextField
                id="post-category"
                label="Category (optional)"
                maxLength={40}
                list="post-categories"
                value={form.category}
                onChange={(event) => setForm({ category: event.target.value })}
                error={errors.category}
                hint={`Suggestions: ${POST_CATEGORIES.join(", ")}.`}
              />
              <datalist id="post-categories">
                {POST_CATEGORIES.map((category) => (
                  <option key={category} value={category} />
                ))}
              </datalist>
              <TextField
                id="post-tags"
                label="Tags (optional)"
                maxLength={500}
                value={form.tags}
                placeholder="[home loan], [documents]"
                onChange={(event) => setForm({ tags: event.target.value })}
                error={errors.tags ?? errors["tags.0"]}
                hint="Separate tags with commas. Up to 10."
              />
            </Panel>
          </fieldset>
        </TabPanel>
        <TabPanel idPrefix="post" tabId="seo" selected={tab === "seo"}>
          <SeoFields
            value={form.seo}
            onChange={(patch) => setForm({ seo: { ...form.seo, ...patch } })}
            errors={errors}
            warnings={post?.seo_warnings ?? []}
            path={post?.path ?? `/blog/${shownSlug || "[web-address]"}`}
            fallbackTitle={`${form.title.trim() || "[Post title]"} | Empire`}
            fallbackDescription={form.excerpt.trim() || "[Search description]"}
            canEdit={canWrite && can("seo.manage")}
            canUpload={canUpload}
            onBusyChange={(busy) => uploads.report("seo", busy)}
          />
        </TabPanel>
      </div>

      {post ? (
        <PostPublishing
          post={post}
          actions={actions}
          dirty={dirty}
          canWrite={canWrite}
          canPublish={canPublish}
        />
      ) : null}
      {actions.dialogs}
      {leaveDialog}
    </>
  );
}
