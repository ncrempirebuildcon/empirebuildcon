"use client";
/**
 * One Settings section's form (board NoirCmsSettings): labelled fields in a two-column grid,
 * "Discard changes" and "Save changes" at the bottom, and the API's messages at their fields.
 *
 * How it works:
 *   1. Each field names its settings group and key (`company.gstin`). The form keeps a draft of
 *      text values; empty means "not set" and is sent as null.
 *   2. Save sends one PATCH per group that changed, with only the changed keys (`onSave`).
 *      A 422 from the API puts each message at its field; the first group's failure stops the
 *      rest, so nothing is half-saved without saying so.
 *   3. Unsaved changes are reported to the screen (one guard for the whole screen).
 *   4. Read-only roles see the same fields, disabled, with the reason above them.
 */
import { Fragment, useState, type ReactNode } from "react";
import { Alert, Button, NumberField, TextField, Textarea, cx } from "@empire/ui";
import { fieldErrors, problemMessage, type FieldErrors } from "@/lib/problems";
import { useReportDirty } from "@/components/admin/useUnsavedChanges";
import {
  draftOf,
  fieldId,
  patchesOf,
  type FieldDef,
  type GroupPatches,
  type GroupValues,
} from "./fieldValues";

export type { FieldDef, FieldKind, GroupPatches, GroupValues } from "./fieldValues";

export interface GroupFormProps {
  /** Accessible name of the form, e.g. "Company settings". */
  label: string;
  fields: readonly FieldDef[];
  values: GroupValues;
  readOnly: boolean;
  /** Why the fields are read-only, shown above them. */
  readOnlyReason?: string;
  /** Saves the changed groups, one PATCH each; throws the API's problem on failure. */
  onSave: (patches: GroupPatches) => Promise<void>;
  onDirtyChange: (dirty: boolean) => void;
  /** Content above the fields (notes, locked switches). */
  before?: ReactNode;
  /** Content between the fields and the buttons. */
  after?: ReactNode;
  /** Sub-headings shown before a field, keyed by its id (`group.key`), e.g. "Social links". */
  headings?: Readonly<Record<string, string>>;
}

export function GroupForm({
  label,
  fields,
  values,
  readOnly,
  readOnlyReason,
  onSave,
  onDirtyChange,
  before,
  after,
  headings = {},
}: GroupFormProps) {
  const [saved, setSaved] = useState(() => draftOf(fields, values));
  const [draft, setDraft] = useState(saved);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const patches = patchesOf(fields, draft, saved);
  const dirty = Object.keys(patches).length > 0;
  useReportDirty(onDirtyChange, dirty);

  async function save() {
    if (busy || !dirty || readOnly) return;
    setBusy(true);
    setError(null);
    setErrors({});
    setNotice(null);
    try {
      await onSave(patches);
      setSaved(draft);
      setNotice("Saved. The change is in the audit log.");
    } catch (err) {
      const found = fieldErrors(err);
      // The API names a field by its key inside the group; the form keys fields "group.key".
      const mapped: FieldErrors = {};
      for (const [path, message] of Object.entries(found)) {
        const match = fields.find(
          (f) => fieldId(f) === path || f.key === path || path.endsWith(`.${f.key}`),
        );
        mapped[match ? fieldId(match) : path] = message;
      }
      setErrors(mapped);
      setError(problemMessage(err, "Couldn't save these settings."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      noValidate
      aria-label={label}
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}
      className="flex flex-col gap-4.5"
    >
      {readOnly && readOnlyReason ? <Alert tone="info">{readOnlyReason}</Alert> : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      {notice && !dirty ? <Alert tone="success">{notice}</Alert> : null}
      {before}
      <fieldset disabled={readOnly || busy} className="grid min-w-0 gap-4 md:grid-cols-2">
        <legend className="sr-only">{label}</legend>
        {fields.map((field) => {
          const id = fieldId(field);
          const heading = headings[id];
          return (
            <Fragment key={id}>
              {heading ? (
                <h3 className="pt-2 text-base font-bold md:col-span-2">{heading}</h3>
              ) : null}
              <div className={cx("min-w-0", field.wide && "md:col-span-2")}>
                <SettingField
                  field={field}
                  value={draft[id] ?? ""}
                  error={errors[id]}
                  onChange={(value) => {
                    setDraft((current) => ({ ...current, [id]: value }));
                    setNotice(null);
                  }}
                />
              </div>
            </Fragment>
          );
        })}
      </fieldset>
      {after}
      {readOnly ? null : (
        <div className="flex flex-wrap justify-end gap-2.5 border-t border-line pt-3.5">
          <Button
            variant="secondary"
            disabled={!dirty || busy}
            onClick={() => {
              setDraft(saved);
              setErrors({});
              setError(null);
            }}
          >
            Discard changes
          </Button>
          <Button type="submit" loading={busy} disabled={!dirty}>
            Save changes
          </Button>
        </div>
      )}
    </form>
  );
}

function SettingField({
  field,
  value,
  error,
  onChange,
}: {
  field: FieldDef;
  value: string;
  error?: string;
  onChange: (value: string) => void;
}) {
  const id = `setting-${field.group}-${field.key}`;
  if (field.kind === "textarea") {
    return (
      <Textarea
        id={id}
        label={field.label}
        hint={field.hint}
        error={error}
        rows={2}
        maxLength={field.maxLength}
        placeholder={field.placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }
  if (field.kind === "number") {
    return (
      <NumberField
        id={id}
        label={field.label}
        hint={field.hint}
        error={error}
        value={value === "" ? null : Number(value)}
        onValueChange={(next) => onChange(next === null ? "" : String(next))}
      />
    );
  }
  const type = field.kind === "id" ? "text" : field.kind;
  return (
    <TextField
      id={id}
      label={field.label}
      hint={field.hint}
      error={error}
      type={type}
      inputMode={field.kind === "tel" ? "tel" : field.kind === "email" ? "email" : undefined}
      autoComplete="off"
      spellCheck={field.kind === "text"}
      maxLength={field.maxLength}
      placeholder={field.placeholder}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      inputClassName={field.kind === "id" ? "font-mono" : undefined}
    />
  );
}
