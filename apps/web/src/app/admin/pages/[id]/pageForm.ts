/**
 * The page editor's own fields (Settings and SEO tabs), converted from the API's `Page` and back
 * into the PATCH body (`PageUpdate`, every field optional).
 *
 * How it works:
 *   1. `toForm` makes strings of everything ("" for empty) and splits the schedule into India
 *      date and time inputs (lib/content/schedule.ts).
 *   2. `toUpdate` sends only the fields that changed. WHY: a system page's kind ("system") can't
 *      be sent back (staff may only choose standard, landing or legal), and a smaller PATCH keeps
 *      the audit log's before/after diff to what the user really changed.
 *   3. `checkForm` repeats the rules staff hit most (title, web address, schedule order), so the
 *      problem shows next to its field before saving; the API checks everything again.
 */
import type { Schema } from "@/lib/api";
import type { PageKind } from "@/lib/content/labels";
import {
  fromInstant,
  toInstant,
  type IstDateTime,
  type ScheduleProblem,
} from "@/lib/content/schedule";
import { sameSeo, toSeo, toSeoForm, type SeoForm } from "@/lib/content/seo";
import { slugProblem } from "@/lib/content/slug";
import type { Media } from "@/lib/media/upload";
import type { FieldErrors } from "@/lib/problems";

export type Page = Schema<"Page">;
export type PageUpdate = Schema<"PageUpdate">;

export interface PageForm {
  title: string;
  slug: string;
  kind: PageKind;
  show_in_nav: boolean;
  nav_order: number | null;
  legal_version: string;
  publish_at: IstDateTime;
  unpublish_at: IstDateTime;
  seo: SeoForm;
}

export function toForm(page: Page, media: (id: string) => Media | null): PageForm {
  return {
    title: page.title,
    slug: page.slug,
    kind: page.kind,
    show_in_nav: page.show_in_nav,
    nav_order: page.nav_order ?? null,
    legal_version: page.legal_version ?? "",
    publish_at: fromInstant(page.publish_at),
    unpublish_at: fromInstant(page.unpublish_at),
    seo: toSeoForm(page.seo, media),
  };
}

/** Problems found before saving, keyed like the API's errors ("slug", "publish_at"). */
export interface FormProblems {
  fields: FieldErrors;
  publish_at: ScheduleProblem | null;
  unpublish_at: ScheduleProblem | null;
}

export function checkForm(form: PageForm): FormProblems {
  const fields: FieldErrors = {};
  if (!form.title.trim()) fields.title = "Enter the page title.";
  const slug = slugProblem(form.slug);
  if (slug) fields.slug = slug;
  const publish = toInstant(form.publish_at, "00:00");
  const unpublish = toInstant(form.unpublish_at, "23:59");
  let unpublishProblem = unpublish.problem;
  if (
    !unpublishProblem &&
    publish.instant &&
    unpublish.instant &&
    unpublish.instant <= publish.instant
  ) {
    unpublishProblem = { field: "date", message: "Take it down after it goes live." };
  }
  return { fields, publish_at: publish.problem, unpublish_at: unpublishProblem };
}

export const hasProblems = (problems: FormProblems) =>
  Object.keys(problems.fields).length > 0 ||
  problems.publish_at !== null ||
  problems.unpublish_at !== null;

/** The PATCH body: only what changed from `saved`. Call after `checkForm` found nothing. */
export function toUpdate(form: PageForm, saved: PageForm): PageUpdate {
  const body: PageUpdate = {};
  if (form.title.trim() !== saved.title) body.title = form.title.trim();
  if (form.slug !== saved.slug) body.slug = form.slug;
  if (form.kind !== saved.kind && form.kind !== "system") body.kind = form.kind;
  if (form.show_in_nav !== saved.show_in_nav) body.show_in_nav = form.show_in_nav;
  if (form.nav_order !== saved.nav_order) body.nav_order = form.nav_order;
  if (form.legal_version.trim() !== saved.legal_version) {
    body.legal_version = form.legal_version.trim() || null;
  }
  const publish = toInstant(form.publish_at, "00:00").instant;
  if (publish !== toInstant(saved.publish_at, "00:00").instant) body.publish_at = publish;
  const unpublish = toInstant(form.unpublish_at, "23:59").instant;
  if (unpublish !== toInstant(saved.unpublish_at, "23:59").instant) body.unpublish_at = unpublish;
  if (!sameSeo(form.seo, saved.seo)) body.seo = toSeo(form.seo);
  return body;
}

/** True when nothing in the form would be saved. */
export const sameForm = (a: PageForm, b: PageForm) => Object.keys(toUpdate(a, b)).length === 0;
