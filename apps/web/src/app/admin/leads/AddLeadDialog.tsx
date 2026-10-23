"use client";
/**
 * "Add lead": a lead taken by phone, WhatsApp or in person (board NoirCmsLeads "+ Add lead";
 * `POST /admin/leads`, needs `leads.update`). On success it opens the new lead.
 *
 * COMPLIANCE: a lead without a consent record is refused (AGENTS.md "Consent"). A manual lead
 * has no ticked box, so staff must say how the person agreed to be contacted ("Verbal on phone
 * call, 23 Oct"); the field is required here and by the API, and is stored with the lead's
 * consent record. Nothing about marketing consent is assumed.
 */
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Alert, Button, ConfirmDialog, Dialog, Select, TextField, Textarea } from "@empire/ui";
import { api, call } from "@/lib/api";
import { LEAD_SOURCE, MANUAL_SOURCES, type LeadSource } from "@/lib/leads/labels";
import { fieldErrors, problemMessage, type FieldErrors } from "@/lib/problems";
import { leadPath } from "@/lib/routes";
import { useUnsavedChanges } from "@/components/admin/useUnsavedChanges";
import type { SelectOption } from "@empire/ui";

export interface AddLeadDialogProps {
  open: boolean;
  onClose: () => void;
  projects: SelectOption[];
  /**
   * Staff the lead can be given to (with `leads.assign`). Empty for a role that can't assign:
   * the lead is then theirs (the API's rule when `owner_user_id` is left out).
   */
  owners: SelectOption[];
}

/** The owner choice that sends `owner_user_id: null`: the shared sales inbox. */
const SALES_INBOX = "unassigned";

interface Draft {
  name: string;
  phone: string;
  email: string;
  project_id: string;
  source: LeadSource;
  message: string;
  owner_user_id: string;
  consent_note: string;
}

const EMPTY: Draft = {
  name: "",
  phone: "",
  email: "",
  project_id: "",
  source: "phone",
  message: "",
  owner_user_id: "",
  consent_note: "",
};

/** Checks in the browser before sending; the API checks everything again (phone rules too). */
function validate(draft: Draft): FieldErrors {
  const errors: FieldErrors = {};
  if (draft.name.trim().length < 2) errors.name = "Enter the person's name.";
  if (!draft.phone.trim()) errors.phone = "Enter their mobile number.";
  if (draft.consent_note.trim().length < 3) {
    errors.consent_note = "Say how they agreed to be contacted, e.g. “Verbal on phone call”.";
  }
  return errors;
}

export function AddLeadDialog({ open, onClose, projects, owners }: AddLeadDialogProps) {
  const router = useRouter();
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));
  // Typed but not added yet: closing the tab or signing out asks first (useUnsavedChanges), and
  // Cancel or Escape asks "Discard this lead?" instead of throwing the typing away.
  const dirty =
    open && (Object.keys(EMPTY) as Array<keyof Draft>).some((key) => draft[key] !== EMPTY[key]);
  const { dialog: leaveDialog } = useUnsavedChanges(dirty);
  const [askDiscard, setAskDiscard] = useState(false);
  const close = () => (dirty && !busy ? setAskDiscard(true) : onClose());

  async function submit() {
    if (busy) return;
    const found = validate(draft);
    setErrors(found);
    setError(null);
    if (Object.keys(found).length > 0) {
      document.getElementById(`add-lead-${Object.keys(found)[0]}`)?.focus();
      return;
    }
    setBusy(true);
    try {
      const lead = await call(
        api.POST("/api/v1/admin/leads", {
          body: {
            name: draft.name.trim(),
            phone: draft.phone.trim(),
            email: draft.email.trim() || null,
            project_id: draft.project_id || null,
            source: draft.source,
            message: draft.message.trim() || null,
            // Left out: the lead is the author's. "Sales inbox": null (needs leads.assign).
            ...(draft.owner_user_id
              ? { owner_user_id: draft.owner_user_id === SALES_INBOX ? null : draft.owner_user_id }
              : {}),
            consent_note: draft.consent_note.trim(),
          },
        }),
      );
      router.push(leadPath(lead.id));
    } catch (err) {
      setBusy(false);
      setErrors(fieldErrors(err));
      setError(problemMessage(err, "Couldn't add the lead."));
    }
  }

  const form = (
    <Dialog
      open={open}
      title="Add a lead"
      wide
      busy={busy}
      onClose={close}
      onSubmit={() => void submit()}
      footer={
        <>
          <Button variant="secondary" disabled={busy} onClick={close}>
            Cancel
          </Button>
          <Button type="submit" loading={busy}>
            Add lead
          </Button>
        </>
      }
    >
      <p className="text-small">
        For a call, a WhatsApp chat or a walk-in. Website enquiries arrive on their own.
      </p>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          id="add-lead-name"
          label="Name"
          required
          autoComplete="off"
          maxLength={80}
          value={draft.name}
          error={errors.name}
          onChange={(event) => set("name", event.target.value)}
        />
        <TextField
          id="add-lead-phone"
          label="Mobile"
          required
          type="tel"
          inputMode="tel"
          autoComplete="off"
          maxLength={20}
          hint="Any Indian format, e.g. 98765 43210 or +91-98765-43210. Landlines with the STD code."
          value={draft.phone}
          error={errors.phone}
          onChange={(event) => set("phone", event.target.value)}
        />
        <TextField
          id="add-lead-email"
          label="Email (optional)"
          type="email"
          autoComplete="off"
          maxLength={200}
          value={draft.email}
          error={errors.email}
          onChange={(event) => set("email", event.target.value)}
        />
        <Select
          id="add-lead-source"
          label="How they got in touch"
          value={draft.source}
          options={MANUAL_SOURCES.map((source) => ({ value: source, label: LEAD_SOURCE[source] }))}
          error={errors.source}
          onChange={(event) => set("source", event.target.value as LeadSource)}
        />
        <Select
          id="add-lead-project_id"
          label="Project"
          value={draft.project_id}
          placeholder="General enquiry (no project)"
          options={projects}
          error={errors.project_id}
          onChange={(event) => set("project_id", event.target.value)}
        />
        {owners.length > 0 ? (
          <Select
            id="add-lead-owner_user_id"
            label="Owner"
            value={draft.owner_user_id}
            placeholder="Me"
            options={[{ value: SALES_INBOX, label: "Sales inbox (unassigned)" }, ...owners]}
            error={errors.owner_user_id}
            onChange={(event) => set("owner_user_id", event.target.value)}
          />
        ) : (
          <p className="self-end text-caption text-muted">The lead will be yours.</p>
        )}
      </div>
      <Textarea
        id="add-lead-message"
        label="What they asked about (optional)"
        rows={3}
        maxLength={2000}
        value={draft.message}
        error={errors.message}
        onChange={(event) => set("message", event.target.value)}
      />
      <TextField
        id="add-lead-consent_note"
        label="How they agreed to be contacted"
        required
        maxLength={500}
        hint="Stored as the lead's consent record, e.g. “Verbal on phone call, 23 Oct”. It doesn't cover marketing messages."
        value={draft.consent_note}
        error={errors.consent_note}
        onChange={(event) => set("consent_note", event.target.value)}
      />
    </Dialog>
  );
  return (
    <>
      {form}
      <ConfirmDialog
        open={askDiscard}
        title="Discard this lead?"
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        tone="danger"
        onCancel={() => setAskDiscard(false)}
        onConfirm={() => {
          setAskDiscard(false);
          onClose();
        }}
      >
        What you typed hasn&apos;t been saved. If you close the form now, it is lost.
      </ConfirmDialog>
      {leaveDialog}
    </>
  );
}
