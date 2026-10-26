"use client";
/**
 * Settings → Consent texts (Phase 4 part 5 spec; D-017, ARCHITECTURE §8 "Consent"): the wording
 * visitors agree to on each form, per purpose. Every version is listed with which one is
 * current, DRAFT markers (wording still awaiting the owner's approval), and who published it
 * when. "New version" drafts a new text (published texts are never edited); Publish makes a
 * version current. The dashboard's "Needs attention" consent tasks link here (`?tab=consent`).
 *
 * COMPLIANCE (D-017): production refuses to publish a text still marked "[DRAFT"; development
 * and tests allow it so the flow can be tried. The refusal comes from the API and is shown as it
 * comes; the screen also says so before the click. Leads store the version they agreed to.
 */
import { useState, type FormEvent } from "react";
import {
  Alert,
  Button,
  Chip,
  ConfirmDialog,
  Select,
  TextField,
  Textarea,
  lengthText,
} from "@empire/ui";
import { api, call, type Schema } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { fieldErrors, problemMessage, type FieldErrors } from "@/lib/problems";
import { ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { useLoad } from "@/components/admin/useLoad";
import { useReportDirty } from "@/components/admin/useUnsavedChanges";
import { useAdminSession } from "../session-context";
import type { SectionProps } from "./sections";

type ConsentText = Schema<"ConsentText">;
type Kind = ConsentText["kind"];

/** What each purpose is for, in plain words. */
export const CONSENT_KINDS: Record<Kind, string> = {
  lead_form: "Enquiry forms (required consent)",
  marketing: "Marketing messages (optional consent)",
  brochure: "Brochure requests",
  cookies: "Cookie banner (Phase 6)",
  chat: "Chat assistant (Phase 7)",
};

const BODY_LIMIT = 5000;
const LABEL_LIMIT = 300;

export function ConsentSection({ onDirtyChange }: SectionProps) {
  const { can } = useAdminSession();
  const canPublish = can("legal.publish");
  const [kind, setKind] = useState<Kind>("lead_form");
  const summaries = useLoad("settings:consent-kinds", () =>
    call(api.GET("/api/v1/admin/consent-texts/current")),
  );
  const load = useLoad(`settings:consent:${kind}`, () =>
    call(api.GET("/api/v1/admin/consent-texts", { params: { query: { kind } } })),
  );
  const summary = summaries.data?.find((item) => item.kind === kind);
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const versions = [...(load.data ?? [])].sort((a, b) => b.version - a.version);
  const current = versions.find((v) => v.is_current) ?? null;

  return (
    <div className="flex flex-col gap-4.5">
      <div className="flex flex-wrap items-end gap-3">
        <Select
          label="Purpose"
          value={kind}
          options={(Object.keys(CONSENT_KINDS) as Kind[]).map((key) => {
            const item = summaries.data?.find((entry) => entry.kind === key);
            const label = item?.label ?? CONSENT_KINDS[key];
            return {
              value: key,
              label: item
                ? `${label} · ${item.current_version ? `version ${item.current_version} live` : "nothing live"}`
                : label,
            };
          })}
          onChange={(event) => {
            const next = (Object.keys(CONSENT_KINDS) as Kind[]).find(
              (k) => k === event.target.value,
            );
            if (next) {
              setKind(next);
              setCreating(false);
              setMessage(null);
            }
          }}
          className="min-w-0 flex-[1_1_260px]"
        />
        {canPublish && !creating ? (
          <Button variant="secondary" className="mb-0.75" onClick={() => setCreating(true)}>
            New version
          </Button>
        ) : null}
      </div>
      {summary?.purpose ? (
        <p className="-mt-2.5 text-caption text-muted">{summary.purpose}</p>
      ) : null}
      {!canPublish ? (
        <Alert tone="info">
          You can read these texts. Drafting and publishing them needs the legal.publish permission.
        </Alert>
      ) : null}
      {message ? <Alert tone="success">{message}</Alert> : null}
      {summary?.has_unpublished_newer && !message ? (
        <Alert tone="info">
          A newer version than the live one is waiting to be published (version{" "}
          {summary.latest_version}).
        </Alert>
      ) : null}
      {creating ? (
        <NewVersionForm
          key={kind}
          kind={kind}
          from={current}
          onDirtyChange={onDirtyChange}
          onCancel={() => setCreating(false)}
          onCreated={async (text) => {
            setCreating(false);
            setMessage(
              `Version ${text.version} is saved as a draft. Publish it when the owner has approved the wording.`,
            );
            await Promise.all([load.refresh(), summaries.refresh()]).catch(() => undefined);
          }}
        />
      ) : null}
      {load.error ? (
        <ErrorPanel
          message={problemMessage(load.error, "Couldn't load the consent texts.")}
          onRetry={load.reload}
        />
      ) : !load.data ? (
        <LoadingPanel label="Loading consent texts…" rows={3} />
      ) : versions.length === 0 ? (
        <Alert tone="info" title="No text for this purpose yet">
          {kind === "lead_form"
            ? "Without a published enquiry text, the website's forms can't take enquiries. Draft one with “New version”."
            : "Draft one with “New version” when this purpose is needed."}
        </Alert>
      ) : (
        <ol aria-label={`Versions: ${CONSENT_KINDS[kind]}`} className="flex flex-col gap-3">
          {versions.map((text) => (
            <VersionCard
              key={text.id}
              text={text}
              canPublish={canPublish}
              onPublished={async (published) => {
                setMessage(
                  `Version ${published.version} is now the current text. New leads record this version.`,
                );
                await Promise.all([load.refresh(), summaries.refresh()]).catch(() => undefined);
              }}
            />
          ))}
        </ol>
      )}
    </div>
  );
}

function VersionCard({
  text,
  canPublish,
  onPublished,
}: {
  text: ConsentText;
  canPublish: boolean;
  onPublished: (text: ConsentText) => Promise<void>;
}) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const publishedBy = text.published_by;

  async function publish() {
    setBusy(true);
    setError(null);
    try {
      const published = await call(
        api.POST("/api/v1/admin/consent-texts/{id}/publish", { params: { path: { id: text.id } } }),
      );
      setAsking(false);
      await onPublished(published);
    } catch (err) {
      setError(problemMessage(err, "Couldn't publish this version."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="flex flex-col gap-2.5 rounded-card border border-line-strong bg-noir-700 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <strong className="text-ivory">Version {text.version}</strong>
        {text.is_current ? (
          <Chip variant="published">Current</Chip>
        ) : text.published_at ? (
          <Chip variant="archived">Earlier version</Chip>
        ) : (
          <Chip variant="draft">Not published</Chip>
        )}
        {text.is_draft_text ? <Chip variant="sample">DRAFT TEXT</Chip> : null}
      </div>
      <p className="text-caption text-muted">
        {text.published_at
          ? `Published ${formatDateTime(text.published_at)}${publishedBy ? ` by ${publishedBy.name}` : ""}`
          : `Drafted ${formatDateTime(text.created_at)}${text.created_by ? ` by ${text.created_by.name}` : ""}`}
      </p>
      <div className="flex flex-col gap-1">
        <span className="text-caption font-semibold text-ivory">Checkbox label</span>
        <p className="text-small">{text.checkbox_label}</p>
      </div>
      <details className="text-small">
        <summary className="min-h-11 cursor-pointer content-center font-bold text-gold-300">
          Full text
        </summary>
        <p className="mt-1.5 whitespace-pre-wrap [overflow-wrap:anywhere]">{text.body}</p>
      </details>
      {text.is_draft_text && !text.published_at ? (
        <p className="text-caption text-body">
          This wording still carries the [DRAFT] mark: it waits for the owner&apos;s approval
          (D-017). The live site refuses to publish it; this development copy allows it so the flow
          can be tried.
        </p>
      ) : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      {canPublish && !text.published_at ? (
        <div>
          <Button onClick={() => setAsking(true)}>Publish version {text.version}</Button>
        </div>
      ) : null}
      <ConfirmDialog
        open={asking}
        title={`Publish version ${text.version}?`}
        confirmLabel="Publish"
        busy={busy}
        error={error}
        onCancel={() => {
          setAsking(false);
          setError(null);
        }}
        onConfirm={() => void publish()}
      >
        The forms show this wording at once, and every new lead records this version. Published
        texts can&apos;t be edited; a change needs a new version.
      </ConfirmDialog>
    </li>
  );
}

function NewVersionForm({
  kind,
  from,
  onDirtyChange,
  onCancel,
  onCreated,
}: {
  kind: Kind;
  from: ConsentText | null;
  onDirtyChange: (dirty: boolean) => void;
  onCancel: () => void;
  onCreated: (text: ConsentText) => Promise<void>;
}) {
  const start = { body: from?.body ?? "", checkbox_label: from?.checkbox_label ?? "" };
  const [body, setBody] = useState(start.body);
  const [label, setLabel] = useState(start.checkbox_label);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  useReportDirty(onDirtyChange, body !== start.body || label !== start.checkbox_label);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const found: FieldErrors = {};
    if (!label.trim()) found.checkbox_label = "Enter the words next to the checkbox.";
    if (!body.trim()) found.body = "Enter the consent text.";
    if ([...label].length > LABEL_LIMIT)
      found.checkbox_label = `Use at most ${LABEL_LIMIT} characters.`;
    if ([...body].length > BODY_LIMIT) found.body = `Use at most ${BODY_LIMIT} characters.`;
    setErrors(found);
    setError(null);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    try {
      const text = await call(
        api.POST("/api/v1/admin/consent-texts", {
          body: { kind, body: body.trim(), checkbox_label: label.trim() },
        }),
      );
      await onCreated(text);
    } catch (err) {
      setErrors(fieldErrors(err));
      setError(problemMessage(err, "Couldn't save the new version."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      noValidate
      aria-label="New consent text version"
      onSubmit={onSubmit}
      className="flex flex-col gap-4 rounded-card border border-gold-line-strong bg-noir-900 p-4"
    >
      <h3 className="text-base font-bold">New version · {CONSENT_KINDS[kind]}</h3>
      <p className="text-caption text-muted">
        {from ? `Starts from version ${from.version}. ` : ""}Plain text only. Keep “[DRAFT” at the
        start until the owner approves the wording; the live site won&apos;t publish it before.
      </p>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <fieldset disabled={busy} className="flex min-w-0 flex-col gap-4">
        <legend className="sr-only">New version</legend>
        <TextField
          label="Checkbox label"
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          error={errors.checkbox_label}
          hint={lengthText(label, LABEL_LIMIT)}
        />
        <Textarea
          label="Consent text"
          rows={8}
          value={body}
          onChange={(event) => setBody(event.target.value)}
          error={errors.body}
          hint={lengthText(body, BODY_LIMIT)}
        />
      </fieldset>
      <div className="flex flex-wrap gap-2.5">
        <Button type="submit" loading={busy}>
          Save as draft
        </Button>
        <Button variant="secondary" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
