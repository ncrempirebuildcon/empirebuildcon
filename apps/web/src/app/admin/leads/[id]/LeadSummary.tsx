"use client";
/**
 * The top card of the lead detail (board NoirCmsLead "Lead summary"): who it is, the full mobile
 * number with Call and WhatsApp, the reference and when it came in, the project and source, the
 * owner (changeable with `leads.assign`), "Mark unread" and the spam flag.
 *
 * COMPLIANCE: this is the one place the full number is shown (lists mask it), behind the same
 * object-level check as the rest of the lead (SECURITY.md §1, §8).
 */
import { useState } from "react";
import {
  Alert,
  Button,
  Chip,
  LiveRegion,
  Select,
  formatPhone,
  type SelectOption,
} from "@empire/ui";
import type { Schema } from "@/lib/api";
import { updateLead } from "@/lib/leads/api";
import { formatDateTime } from "@/lib/dates";
import { LEAD_SOURCE, type Lead } from "@/lib/leads/labels";
import { initials } from "@/lib/leads/people";
import { problemMessage } from "@/lib/problems";
import { ContactLinks } from "@/components/admin/leads/ContactLinks";

export interface LeadSummaryProps {
  lead: Lead;
  owners: SelectOption[];
  canAssign: boolean;
  canUpdate: boolean;
  /** Called with the saved lead after a change here. */
  onSaved: (lead: Lead) => void;
  /** "Mark unread": the caller sends it, refreshes, and goes back to the inbox (or stays). */
  onMarkUnread: () => Promise<void>;
}

const UNASSIGNED = "unassigned";

export function LeadSummary({
  lead,
  owners,
  canAssign,
  canUpdate,
  onSaved,
  onMarkUnread,
}: LeadSummaryProps) {
  const [busy, setBusy] = useState<"owner" | "spam" | "unread" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const erased = Boolean(lead.erased_at);
  const ownerValue = lead.owner?.id ?? UNASSIGNED;
  // The current owner may not be in the list (e.g. a deactivated account): keep them visible.
  const ownerOptions: SelectOption[] = [
    { value: UNASSIGNED, label: "Unassigned (sales inbox)" },
    ...owners,
    ...(lead.owner && !owners.some((o) => o.value === lead.owner?.id)
      ? [{ value: lead.owner.id, label: lead.owner.name }]
      : []),
  ];

  async function patch(
    kind: "owner" | "spam",
    body: Schema<"LeadUpdate">,
    said: (saved: Lead) => string,
  ) {
    setBusy(kind);
    setError(null);
    try {
      const saved = await updateLead(lead.id, body);
      setAnnouncement(said(saved));
      onSaved(saved);
    } catch (err) {
      setError(problemMessage(err, "Couldn't save the change."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section
      aria-label="Lead summary"
      className="flex flex-col gap-4 rounded-card border border-gold-line-strong bg-noir-800 px-5 py-4.5"
    >
      <LiveRegion message={announcement} />
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3.5">
          <span
            aria-hidden="true"
            className="flex size-13 shrink-0 items-center justify-center rounded-pill border border-gold-500 bg-noir-700 font-display text-[19px] font-semibold text-gold-300"
          >
            {erased ? "–" : initials(lead.name)}
          </span>
          <div className="flex min-w-0 flex-col gap-0.5">
            <div className="flex flex-wrap items-center gap-2.5">
              <strong className="text-xl [overflow-wrap:anywhere] text-ivory">{lead.name}</strong>
              {lead.is_sample ? <Chip variant="sample">SAMPLE</Chip> : null}
              {lead.is_spam ? <Chip variant="archived">Spam</Chip> : null}
              {erased ? <Chip variant="archived">Personal data erased</Chip> : null}
            </div>
            <span className="text-small tabular-nums">
              {erased ? "Number erased" : formatPhone(lead.phone_e164)} · ref{" "}
              <span className="font-mono">{lead.reference}</span> · received{" "}
              {formatDateTime(lead.created_at)}
            </span>
            <span className="text-caption text-muted">
              {lead.project?.name ?? "General enquiry"} · came from {LEAD_SOURCE[lead.source]}
              {lead.utm.campaign ? ` (${lead.utm.campaign})` : ""}
            </span>
          </div>
        </div>
        <div className="flex flex-wrap items-end gap-2.5">
          {erased ? null : <ContactLinks phone={lead.phone_e164} name={lead.name} />}
          {canAssign ? (
            <Select
              id="lead-owner"
              label="Owner"
              value={ownerValue}
              disabled={busy === "owner"}
              options={ownerOptions}
              hint="Only admins can change the owner"
              onChange={(event) => {
                const value = event.target.value;
                const label = ownerOptions.find((o) => o.value === value)?.label ?? "";
                void patch("owner", { owner_user_id: value === UNASSIGNED ? null : value }, () =>
                  value === UNASSIGNED
                    ? "Lead moved to the sales inbox."
                    : `Owner changed to ${label}.`,
                );
              }}
              className="min-w-48"
            />
          ) : (
            <p className="text-small">
              Owner: <strong className="text-ivory">{lead.owner?.name ?? "Unassigned"}</strong>
            </p>
          )}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2.5 border-t border-line pt-3.5">
        <Button
          variant="secondary"
          loading={busy === "unread"}
          onClick={async () => {
            setBusy("unread");
            setError(null);
            try {
              await onMarkUnread();
              // Said here too, for when unsaved work keeps the user on this page.
              setAnnouncement("Marked unread.");
            } catch (err) {
              setError(problemMessage(err, "Couldn't mark the lead unread."));
            } finally {
              setBusy(null);
            }
          }}
        >
          Mark unread
        </Button>
        {canUpdate && !erased ? (
          <Button
            variant="secondary"
            loading={busy === "spam"}
            onClick={() =>
              void patch("spam", { is_spam: !lead.is_spam }, (saved) =>
                saved.is_spam
                  ? "Marked as spam. It no longer shows in the inbox."
                  : "No longer marked as spam.",
              )
            }
          >
            {lead.is_spam ? "Not spam" : "Mark as spam"}
          </Button>
        ) : null}
        <span className="text-caption text-muted">
          {lead.is_spam
            ? "Spam leads are hidden from the inbox and the counts."
            : "Opening a lead marks it read for everyone."}
        </span>
      </div>
      {error ? <Alert tone="error">{error}</Alert> : null}
    </section>
  );
}
