"use client";
/**
 * The facts of one lead on its detail page (board NoirCmsLead), in three panels:
 *
 * - Enquiry: project and configuration, how they reached us, what they wrote, and what sales
 *   learnt on the phone (interest, budget, email), which staff with `leads.update` can edit.
 *   Lead forms ask only for name and mobile, so those are "from call notes" (DESIGN_SYSTEM §12).
 * - Consent record (read-only): the contact consent with the text version, the exact checkbox
 *   label shown and when it was given, or, for a lead added by staff, how consent was obtained;
 *   and whether the optional marketing box was ticked.
 * - Source and campaign: UTM tags, which click IDs came with the visit, the landing page and the
 *   referrer.
 *
 * COMPLIANCE: the consent record is never editable here (DPDP Act; AGENTS.md "Consent").
 * SECURITY: page and referrer addresses become links only when they are http(s) or a site path,
 * so a stored `javascript:` address can never run in a staff browser (the API refuses them too).
 */
import Link from "next/link";
import { useState, type ReactNode } from "react";
import {
  Alert,
  Button,
  NumberField,
  Select,
  TextField,
  formatInr,
  type SelectOption,
} from "@empire/ui";
import type { Schema } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { updateLead } from "@/lib/leads/api";
import { LEAD_SOURCE, type Lead } from "@/lib/leads/labels";
import { fieldErrors, problemMessage, type FieldErrors } from "@/lib/problems";
import { projectPath } from "@/lib/routes";
import { Panel } from "@/components/admin/states";
import { useReportDirty } from "@/components/admin/useUnsavedChanges";

const CLICK_IDS = ["gclid", "gbraid", "wbraid", "fbclid", "msclkid"] as const;
const UTM_KEYS = ["source", "medium", "campaign", "term", "content"] as const;

function Facts({ children }: { children: ReactNode }) {
  return (
    <dl className="grid grid-cols-[112px_minmax(0,1fr)] gap-x-3 gap-y-2 text-small">{children}</dl>
  );
}

function Fact({ term, children }: { term: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-muted">{term}</dt>
      <dd className="min-w-0 [overflow-wrap:anywhere]">{children}</dd>
    </>
  );
}

const None = ({ children = "None" }: { children?: ReactNode }) => (
  <span className="text-muted">{children}</span>
);

/** A page address as a link when it is safe to follow; plain text otherwise. */
function SafeLink({ href }: { href: string }) {
  const safe = /^https?:\/\//i.test(href) || (href.startsWith("/") && !href.startsWith("//"));
  return safe ? (
    <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="break-all">
      {href}
    </a>
  ) : (
    <span className="break-all">{href}</span>
  );
}

export function EnquiryPanel({
  lead,
  canUpdate,
  projects,
  onSaved,
  onDirtyChange,
}: {
  lead: Lead;
  canUpdate: boolean;
  projects: SelectOption[];
  onSaved: (lead: Lead) => void;
  /** Whether "Edit details" holds changes not saved yet (for the leave warning). */
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [editing, setEditing] = useState(false);
  const erased = Boolean(lead.erased_at);
  return (
    <Panel
      id="enquiry"
      title="Enquiry"
      actions={
        canUpdate && !erased && !editing ? (
          <Button variant="tertiary" className="min-h-11" onClick={() => setEditing(true)}>
            Edit details
          </Button>
        ) : null
      }
    >
      {editing ? (
        <EditDetails
          lead={lead}
          projects={projects}
          onDirtyChange={onDirtyChange}
          onCancel={() => setEditing(false)}
          onSaved={(saved) => {
            setEditing(false);
            onSaved(saved);
          }}
        />
      ) : (
        <Facts>
          <Fact term="Project">
            {lead.project ? (
              <Link href={projectPath(lead.project.id)} className="font-bold">
                {lead.project.name}
              </Link>
            ) : (
              "General enquiry"
            )}
          </Fact>
          {lead.configuration ? <Fact term="Configuration">{lead.configuration.name}</Fact> : null}
          <Fact term="Came from">{LEAD_SOURCE[lead.source]}</Fact>
          <Fact term="Message">
            {lead.message ? (
              <span className="whitespace-pre-line text-ivory">{lead.message}</span>
            ) : (
              <None>None · the form has no message box or it was left empty</None>
            )}
          </Fact>
          <Fact term="Email">
            {lead.email ? <span className="text-ivory">{lead.email}</span> : <None />}
          </Fact>
          <Fact term="Interest">
            {lead.preferred_bhk !== null && lead.preferred_bhk !== undefined ? (
              <span className="text-ivory">{lead.preferred_bhk} BHK</span>
            ) : (
              <None>Not known yet</None>
            )}
          </Fact>
          <Fact term="Budget">
            {lead.budget_max_inr ? (
              <span className="text-ivory">up to {formatInr(lead.budget_max_inr)}</span>
            ) : (
              <None>Not known yet · the form does not ask</None>
            )}
          </Fact>
          {lead.preferred_contact_time ? (
            <Fact term="Best time">{lead.preferred_contact_time}</Fact>
          ) : null}
          <Fact term="Language">{lead.language === "hi" ? "Hindi" : "English"}</Fact>
        </Facts>
      )}
    </Panel>
  );
}

/**
 * The fields of "Edit details" that differ from the saved lead, as a LeadUpdate.
 * WHY only what changed: every change is written to the activity and the audit log, so an
 * untouched field must not show up there as "changed".
 */
function changedDetails(
  lead: Lead,
  draft: { email: string; bhk: number | null; budget: number | null; projectId: string },
): Schema<"LeadUpdate"> {
  const changes: Schema<"LeadUpdate"> = {};
  const email = draft.email.trim() || null;
  if (email !== (lead.email ?? null)) changes.email = email;
  if (draft.bhk !== (lead.preferred_bhk ?? null)) changes.preferred_bhk = draft.bhk;
  if (draft.budget !== (lead.budget_max_inr ?? null)) changes.budget_max_inr = draft.budget;
  if ((draft.projectId || null) !== (lead.project?.id ?? null)) {
    changes.project_id = draft.projectId || null;
  }
  return changes;
}

function EditDetails({
  lead,
  projects,
  onDirtyChange,
  onCancel,
  onSaved,
}: {
  lead: Lead;
  projects: SelectOption[];
  onDirtyChange?: (dirty: boolean) => void;
  onCancel: () => void;
  onSaved: (lead: Lead) => void;
}) {
  const [email, setEmail] = useState(lead.email ?? "");
  const [bhk, setBhk] = useState<number | null>(lead.preferred_bhk ?? null);
  const [budget, setBudget] = useState<number | null>(lead.budget_max_inr ?? null);
  const [projectId, setProjectId] = useState(lead.project?.id ?? "");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const changes = changedDetails(lead, { email, bhk, budget, projectId });
  useReportDirty(onDirtyChange, Object.keys(changes).length > 0);

  async function save() {
    // The API's rule, checked here first: whole or half BHK from 0.5 to 20.
    if (bhk !== null && (bhk < 0.5 || bhk > 20 || !Number.isInteger(bhk * 2))) {
      setErrors({ preferred_bhk: "Use whole or half BHK from 0.5 to 20, like 2 or 2.5." });
      document.getElementById("lead-bhk")?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    setErrors({});
    if (Object.keys(changes).length === 0) {
      onSaved(lead);
      return;
    }
    try {
      onSaved(await updateLead(lead.id, changes));
    } catch (err) {
      setErrors(fieldErrors(err));
      setError(problemMessage(err, "Couldn't save the details."));
      setBusy(false);
    }
  }

  return (
    <form
      noValidate
      aria-label="Edit enquiry details"
      className="flex flex-col gap-3.5"
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <p className="text-caption text-muted">
        From your calls: lead forms ask only for name and mobile.
      </p>
      <Select
        id="lead-project"
        label="Project"
        value={projectId}
        placeholder="General enquiry (no project)"
        options={projects}
        error={errors.project_id}
        onChange={(event) => setProjectId(event.target.value)}
      />
      <TextField
        id="lead-email"
        label="Email (optional)"
        type="email"
        maxLength={200}
        value={email}
        error={errors.email}
        onChange={(event) => setEmail(event.target.value)}
      />
      <NumberField
        id="lead-bhk"
        label="Interest (BHK)"
        decimals={1}
        hint="Whole or half, like 2 or 2.5"
        value={bhk}
        error={errors.preferred_bhk}
        onValueChange={setBhk}
        suffix="BHK"
      />
      <NumberField
        id="lead-budget"
        label="Budget up to (₹)"
        value={budget}
        error={errors.budget_max_inr}
        onValueChange={setBudget}
        prefix="₹"
        hint={budget ? formatInr(budget) : "Whole rupees, e.g. 1,25,00,000"}
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="flex flex-wrap gap-2.5">
        <Button type="submit" loading={busy}>
          Save details
        </Button>
        <Button variant="secondary" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

export function ConsentPanel({ lead }: { lead: Lead }) {
  const consent = lead.consent;
  const marketing = lead.marketing_consent;
  const manual = !consent.text_version && Boolean(consent.consent_note);
  return (
    <Panel
      id="consent"
      title="Consent record"
      actions={<span className="text-caption text-muted">read-only</span>}
    >
      <ConsentLine given title="Contact about this enquiry: given">
        {manual ? (
          <>Recorded by staff: “{consent.consent_note}”</>
        ) : consent.checkbox_label ? (
          <>“{consent.checkbox_label}”</>
        ) : null}
      </ConsentLine>
      <ConsentLine
        given={Boolean(marketing)}
        title={`News and offers: ${marketing ? "given" : "not given"}`}
      >
        {marketing ? (
          <>
            {marketing.checkbox_label ? <>“{marketing.checkbox_label}” · </> : null}
            {formatDateTime(marketing.consented_at)}
          </>
        ) : (
          "The optional box was left unticked. Don't add them to marketing lists."
        )}
      </ConsentLine>
      <div className="border-t border-line pt-2.5">
        <Facts>
          <Fact term="Consent text">
            {consent.text_version ? (
              <span className="text-ivory">Version {consent.text_version}</span>
            ) : (
              <None>None · added by staff</None>
            )}
          </Fact>
          <Fact term="Recorded">
            <span className="tabular-nums">{formatDateTime(consent.consented_at)} IST</span>
          </Fact>
          <Fact term="Page">
            {consent.page_url ? <SafeLink href={consent.page_url} /> : <None />}
          </Fact>
        </Facts>
      </div>
    </Panel>
  );
}

function ConsentLine({
  given,
  title,
  children,
}: {
  given: boolean;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex items-start gap-2.5 text-small">
      <span
        aria-hidden="true"
        className={
          given
            ? "flex size-5.5 shrink-0 items-center justify-center rounded-[6px] bg-stage-booked-bg font-extrabold text-stage-booked-text"
            : "flex size-5.5 shrink-0 items-center justify-center rounded-[6px] border border-line-strong bg-noir-700 font-extrabold text-muted"
        }
      >
        {given ? "✓" : "–"}
      </span>
      <span>
        <strong className="text-ivory">{title}</strong>
        {children ? <span className="block text-caption">{children}</span> : null}
      </span>
    </div>
  );
}

export function SourcePanel({ lead }: { lead: Lead }) {
  return (
    <Panel id="source" title="Source and campaign">
      <Facts>
        {UTM_KEYS.map((key) => (
          <Fact key={key} term={`utm_${key}`}>
            {lead.utm[key] ? (
              <span className="font-mono text-ivory">{lead.utm[key]}</span>
            ) : (
              <None>none</None>
            )}
          </Fact>
        ))}
        {CLICK_IDS.map((key) => (
          <Fact key={key} term={key}>
            {lead.click_ids[key] ? (
              <span className="font-bold text-palm">Present</span>
            ) : (
              <None>Not present</None>
            )}
          </Fact>
        ))}
        <Fact term="Landing page">
          {lead.page_url ? <SafeLink href={lead.page_url} /> : <None />}
        </Fact>
        <Fact term="Referrer">{lead.referrer ? <SafeLink href={lead.referrer} /> : <None />}</Fact>
      </Facts>
      <p className="text-caption text-muted">
        Campaign tags are kept from the first landing page for 30 days.
      </p>
    </Panel>
  );
}
