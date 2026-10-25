/**
 * The post editor's fields, converted from the API's `Post` and back into the create body
 * (`PostInput`) or the PATCH body (`PostUpdate`, changed fields only, like pageForm.ts).
 */
import type { Schema } from "@/lib/api";
import { parseTags, tagsProblem } from "@/lib/content/posts";
import { sameSeo, toSeo, toSeoForm, type SeoForm } from "@/lib/content/seo";
import { slugProblem } from "@/lib/content/slug";
import type { Media } from "@/lib/media/upload";
import type { FieldErrors } from "@/lib/problems";

export type Post = Schema<"Post">;
export type PostInput = Schema<"PostInput">;
export type PostUpdate = Schema<"PostUpdate">;

export interface PostForm {
  title: string;
  /** "" on a new post means "make it from the title" (the API does). */
  slug: string;
  excerpt: string;
  body: string;
  cover: Media | null;
  category: string;
  /** Tags as typed: one line, comma-separated. */
  tags: string;
  seo: SeoForm;
}

export const EMPTY_POST: PostForm = {
  title: "",
  slug: "",
  excerpt: "",
  body: "",
  cover: null,
  category: "",
  tags: "",
  seo: toSeoForm(null, () => null),
};

export function toForm(post: Post): PostForm {
  const known = (id: string) =>
    post.og_image?.id === id ? post.og_image : post.cover?.id === id ? post.cover : null;
  return {
    title: post.title,
    slug: post.slug,
    excerpt: post.excerpt ?? "",
    body: post.body,
    cover: post.cover ?? null,
    category: post.category ?? "",
    tags: post.tags.join(", "),
    seo: toSeoForm(post.seo, known),
  };
}

const orNull = (value: string) => (value.trim() === "" ? null : value.trim());

/** Problems found before saving, keyed like the API's errors. `isNew` allows an empty slug. */
export function checkForm(form: PostForm, isNew: boolean): FieldErrors {
  const out: FieldErrors = {};
  if (!form.title.trim()) out.title = "Enter the post's title.";
  if (!form.body.trim()) out.body = "Write the post.";
  if (!(isNew && form.slug === "")) {
    const problem = slugProblem(form.slug);
    if (problem) out.slug = problem;
  }
  const tags = tagsProblem(parseTags(form.tags));
  if (tags) out.tags = tags;
  return out;
}

export function toCreate(form: PostForm): PostInput {
  return {
    slug: form.slug || null,
    title: form.title.trim(),
    excerpt: orNull(form.excerpt),
    body: form.body,
    cover_media_id: form.cover?.id ?? null,
    category: orNull(form.category),
    tags: parseTags(form.tags),
    seo: toSeo(form.seo),
    translations: {},
  };
}

export function toUpdate(form: PostForm, saved: PostForm): PostUpdate {
  const body: PostUpdate = {};
  if (form.title.trim() !== saved.title) body.title = form.title.trim();
  if (form.slug !== saved.slug) body.slug = form.slug;
  if (form.excerpt.trim() !== saved.excerpt) body.excerpt = orNull(form.excerpt);
  if (form.body !== saved.body) body.body = form.body;
  if ((form.cover?.id ?? null) !== (saved.cover?.id ?? null)) {
    body.cover_media_id = form.cover?.id ?? null;
  }
  if (form.category.trim() !== saved.category) body.category = orNull(form.category);
  const tags = parseTags(form.tags);
  if (JSON.stringify(tags) !== JSON.stringify(parseTags(saved.tags))) body.tags = tags;
  if (!sameSeo(form.seo, saved.seo)) body.seo = toSeo(form.seo);
  return body;
}

export const sameForm = (a: PostForm, b: PostForm) => Object.keys(toUpdate(a, b)).length === 0;
