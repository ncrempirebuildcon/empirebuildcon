"use client";
/**
 * Start a page: title, web address (suggested from the title until edited) and kind, then open
 * the page editor to add blocks. New pages are always drafts; system pages come with the site
 * and can't be created here (the API refuses the kind too).
 */
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Alert, Button, Select, TextField } from "@empire/ui";
import { api, call } from "@/lib/api";
import { PAGE_KIND, PAGE_KIND_HELP, type PageKind } from "@/lib/content/labels";
import { slugProblem, slugify } from "@/lib/content/slug";
import { fieldErrors, problemMessage, type FieldErrors } from "@/lib/problems";
import { PAGES_PATH, pagePath } from "@/lib/routes";
import { useAdminSession } from "../../session-context";

/** Kinds staff may choose; system pages come with the site (the API's `EditableKind`). */
type EditableKind = Exclude<PageKind, "system">;
const CHOOSABLE: EditableKind[] = ["standard", "landing", "legal"];
const isEditable = (value: string): value is EditableKind =>
  (CHOOSABLE as string[]).includes(value);

export function NewPageForm() {
  const router = useRouter();
  const { can } = useAdminSession();
  const [title, setTitle] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [kind, setKind] = useState<EditableKind>("standard");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});

  if (!can("content.write")) {
    return (
      <Alert tone="info" title="Your role can view pages but not add them.">
        Ask an admin, marketing or a content editor to add the page.{" "}
        <Link href={PAGES_PATH} className="font-bold underline">
          Back to pages
        </Link>
      </Alert>
    );
  }

  const shownSlug = slugEdited ? slug : slugify(title);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setError(null);
    const found: FieldErrors = {};
    if (!title.trim()) found.title = "Enter the page title.";
    const problem = slugProblem(shownSlug);
    if (problem) found.slug = problem;
    if (Object.keys(found).length > 0) {
      setErrors(found);
      return;
    }
    setErrors({});
    setBusy(true);
    try {
      const page = await call(
        api.POST("/api/v1/admin/pages", {
          body: { title: title.trim(), slug: shownSlug, kind, show_in_nav: false },
        }),
      );
      router.push(pagePath(page.id));
    } catch (err) {
      setBusy(false);
      setErrors(fieldErrors(err));
      setError(problemMessage(err, "Couldn't create the page."));
    }
  }

  return (
    <section
      aria-labelledby="new-page-title"
      className="flex max-w-2xl flex-col gap-5 rounded-card border border-line bg-noir-800 p-5 md:p-6"
    >
      <div>
        <h2 id="new-page-title" className="text-[17px] font-bold">
          Start a page
        </h2>
        <p className="mt-1 text-small text-muted">
          It is saved as a draft. You add blocks, menu settings and SEO on the next screen; nothing
          appears on the website until it is published.
        </p>
      </div>
      <form noValidate onSubmit={onSubmit} className="flex flex-col gap-5">
        {error ? <Alert tone="error">{error}</Alert> : null}
        <TextField
          label="Title"
          required
          maxLength={120}
          autoComplete="off"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          error={errors.title}
        />
        <TextField
          label="Web address"
          required
          maxLength={120}
          autoComplete="off"
          value={shownSlug}
          onChange={(event) => {
            setSlugEdited(true);
            setSlug(event.target.value.trim().toLowerCase());
          }}
          error={errors.slug}
          hint={`empirebuildcon.com/${shownSlug || "[web-address]"}`}
        />
        <Select
          label="Kind"
          value={kind}
          options={CHOOSABLE.map((value) => ({ value, label: PAGE_KIND[value] }))}
          onChange={(event) =>
            setKind(isEditable(event.target.value) ? event.target.value : "standard")
          }
          error={errors.kind}
          hint={PAGE_KIND_HELP[kind]}
        />
        <div className="flex flex-wrap gap-3">
          <Button type="submit" loading={busy}>
            Create draft
          </Button>
          <Link href={PAGES_PATH} className="inline-flex min-h-11 items-center px-2 font-bold">
            Cancel
          </Link>
        </div>
      </form>
    </section>
  );
}
