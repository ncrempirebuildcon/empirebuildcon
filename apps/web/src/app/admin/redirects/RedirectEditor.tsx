"use client";
/**
 * The redirect editor beside the list (/admin/redirects): old address, where visitors go, the
 * code (301 or 308) and on/off. Saves with POST or PATCH; the API's loop refusal (409) and chain
 * notices are shown as they come (RedirectsScreen.tsx explains the rules).
 * SECURITY: the API refuses internal paths and other hosts; the checks here only explain early.
 */
import { useState } from "react";
import { Alert, Button, Checkbox, ConfirmDialog, Select, TextField } from "@empire/ui";
import { api, call, type Schema } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { REDIRECT_CODE, type RedirectCode } from "@/lib/content/labels";
import { redirectFromProblem } from "@/lib/content/links";
import { keyOf, optionsOf } from "@/lib/labels";
import { fieldErrors, problemMessage, type FieldErrors } from "@/lib/problems";
import { useReportDirty } from "@/components/admin/useUnsavedChanges";

type Redirect = Schema<"Redirect">;
type Origin = Redirect["origin"];

/** Who made a redirect: by hand, or a renamed page, post or project. */
export const ORIGIN: Record<Origin, string> = {
  manual: "Added by hand",
  page: "Page renamed",
  post: "Post renamed",
  project: "Project renamed",
};

interface RedirectForm {
  from_path: string;
  to_path: string;
  status_code: RedirectCode;
  is_active: boolean;
}

export function RedirectEditor({
  redirect,
  onDirtyChange,
  onSaved,
  onClose,
}: {
  redirect: Redirect | null;
  onDirtyChange: (dirty: boolean) => void;
  onSaved: (saved: Redirect | null, notices: string[]) => Promise<void>;
  onClose: () => void;
}) {
  const start: RedirectForm = redirect
    ? {
        from_path: redirect.from_path,
        to_path: redirect.to_path,
        status_code: redirect.status_code,
        is_active: redirect.is_active,
      }
    : { from_path: "", to_path: "", status_code: "308", is_active: true };
  const [form, setForm] = useState<RedirectForm>(start);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const dirty = JSON.stringify(form) !== JSON.stringify(start);
  useReportDirty(onDirtyChange, dirty);
  const set = (patch: Partial<RedirectForm>) => setForm((current) => ({ ...current, ...patch }));

  async function save() {
    if (busy) return;
    const found: FieldErrors = {};
    const fromProblem = redirectFromProblem(form.from_path);
    if (fromProblem) found.from_path = fromProblem;
    if (!form.to_path.trim())
      found.to_path = "Enter where visitors should go, e.g. /projects/[new-address].";
    if (Object.keys(found).length > 0) {
      setErrors(found);
      setError("Some fields need attention.");
      return;
    }
    setBusy(true);
    setError(null);
    setErrors({});
    try {
      const body = { ...form, from_path: form.from_path.trim(), to_path: form.to_path.trim() };
      const saved = redirect
        ? await call(
            api.PATCH("/api/v1/admin/redirects/{id}", {
              params: { path: { id: redirect.id } },
              body,
            }),
          )
        : await call(api.POST("/api/v1/admin/redirects", { body }));
      await onSaved(saved, [
        `${saved.from_path} → ${saved.to_path} (${saved.status_code}).`,
        ...saved.notices,
      ]);
    } catch (err) {
      // A loop or a taken address is a 409 with the API's own sentence.
      setErrors(fieldErrors(err));
      setError(problemMessage(err, "Couldn't save the redirect."));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!redirect) return;
    setBusy(true);
    setDeleteError(null);
    try {
      await call(
        api.DELETE("/api/v1/admin/redirects/{id}", { params: { path: { id: redirect.id } } }),
      );
      setDeleting(false);
      await onSaved(null, [`The redirect from ${redirect.from_path} was deleted.`]);
    } catch (err) {
      setDeleteError(problemMessage(err, "Couldn't delete the redirect."));
    } finally {
      setBusy(false);
    }
  }

  const title = redirect ? "Edit redirect" : "New redirect";
  return (
    <section
      aria-labelledby="redirect-editor-title"
      className="flex min-w-0 flex-[1_1_320px] flex-col gap-4 rounded-card border border-gold-line-strong bg-noir-800 p-4"
    >
      <h2 id="redirect-editor-title" className="text-[17px] font-bold">
        {title}
      </h2>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <form
        noValidate
        aria-label={title}
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
        className="flex flex-col gap-4"
      >
        <fieldset disabled={busy} className="flex min-w-0 flex-col gap-4">
          <legend className="sr-only">{title}</legend>
          <TextField
            id="redirect-from"
            label="Old address"
            required
            maxLength={500}
            value={form.from_path}
            placeholder="/old-page"
            onChange={(event) => set({ from_path: event.target.value.trim() })}
            error={errors.from_path}
            hint="A path on this site, without the part after ? or #."
          />
          <TextField
            id="redirect-to"
            label="Send visitors to"
            required
            maxLength={500}
            value={form.to_path}
            placeholder="/projects/[new-address]"
            onChange={(event) => set({ to_path: event.target.value.trim() })}
            error={errors.to_path}
            hint="A path on this site, or an https:// address on empirebuildcon.com (stored as its path)."
          />
          <Select
            id="redirect-code"
            label="Kind"
            value={form.status_code}
            options={optionsOf(REDIRECT_CODE)}
            onChange={(event) =>
              set({ status_code: keyOf(REDIRECT_CODE, event.target.value, "308") })
            }
            error={errors.status_code}
            hint="Both tell search engines the page has moved for good. 308 is the default."
          />
          <Checkbox
            checked={form.is_active}
            onChange={(event) => set({ is_active: event.target.checked })}
            label="Redirect is on"
          />
          {redirect ? (
            <p className="text-caption text-muted">
              {ORIGIN[redirect.origin]} · {redirect.hits} hits ·{" "}
              {redirect.last_hit_at
                ? `last hit ${formatDateTime(redirect.last_hit_at)}`
                : "no hits counted yet"}
            </p>
          ) : null}
        </fieldset>
        <div className="flex flex-wrap gap-2.5">
          <Button type="submit" loading={busy} disabled={redirect !== null && !dirty}>
            {redirect ? "Save redirect" : "Add redirect"}
          </Button>
          <Button variant="secondary" disabled={busy} onClick={onClose}>
            Close
          </Button>
          {redirect ? (
            <Button variant="danger" disabled={busy} onClick={() => setDeleting(true)}>
              Delete
            </Button>
          ) : null}
        </div>
      </form>
      <ConfirmDialog
        open={deleting}
        title="Delete this redirect?"
        confirmLabel="Delete redirect"
        tone="danger"
        busy={busy}
        error={deleteError}
        onCancel={() => setDeleting(false)}
        onConfirm={() => void remove()}
      >
        Visitors to {redirect?.from_path} will get “page not found” instead. This can&apos;t be
        undone.
      </ConfirmDialog>
    </section>
  );
}
