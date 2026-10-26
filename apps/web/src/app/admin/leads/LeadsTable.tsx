"use client";
/**
 * The inbox as a table (board NoirCmsLeads, "Table" view): newest first, one row per lead.
 *
 * - Unread rows are bold with a gold dot, and their name starts with "Unread:" for screen
 *   readers, so the cue is never only visual (WCAG 1.3.1, 1.4.1).
 * - The mobile number is masked ("+91 98xxxxxx10"); the full number is on the lead's own page.
 * - The name is the row header and the link to the lead.
 *
 * COMPLIANCE: no full phone numbers, emails or messages in lists (SECURITY.md §8).
 */
import Link from "next/link";
import type { ReactNode } from "react";
import { Chip, Table, maskPhone, type TableColumn } from "@empire/ui";
import { formatAge } from "@empire/ui/format";
import { formatDateTime } from "@/lib/dates";
import { LEAD_SOURCE, type Lead } from "@/lib/leads/labels";
import { leadPath } from "@/lib/routes";
import { StageChip } from "@/components/admin/leads/StageChip";

export interface LeadsTableProps {
  leads: Lead[];
  busy: boolean;
  /** Shown instead of rows when the page is empty. */
  empty: ReactNode;
}

const COLUMNS: TableColumn<Lead>[] = [
  {
    key: "reference",
    header: "Reference",
    className: "whitespace-nowrap font-mono text-caption",
    cell: (lead) => lead.reference,
  },
  {
    key: "name",
    header: "Name",
    rowHeader: true,
    cell: (lead) => <LeadName lead={lead} />,
  },
  {
    key: "phone",
    header: "Mobile",
    className: "whitespace-nowrap tabular-nums",
    cell: (lead) => maskPhone(lead.phone_e164),
  },
  {
    key: "project",
    header: "Project",
    cell: (lead) => lead.project?.name ?? <span className="text-muted">General enquiry</span>,
  },
  { key: "source", header: "Source", cell: (lead) => <LeadSourceCell lead={lead} /> },
  { key: "stage", header: "Stage", cell: (lead) => <StageChip status={lead.status} /> },
  {
    key: "owner",
    header: "Owner",
    className: "whitespace-nowrap",
    cell: (lead) => lead.owner?.name ?? <span className="text-muted">Unassigned</span>,
  },
  {
    key: "age",
    header: "Age",
    className: "whitespace-nowrap text-muted",
    cell: (lead) => (
      <time dateTime={lead.created_at} title={formatDateTime(lead.created_at)}>
        {formatAge(lead.created_at)}
      </time>
    ),
  },
];

function LeadName({ lead }: { lead: Lead }) {
  const unread = !lead.read_at;
  return (
    <span className="flex flex-wrap items-center gap-2">
      {unread ? (
        <span aria-hidden="true" className="size-2 shrink-0 rounded-pill bg-gold-500" />
      ) : null}
      <Link href={leadPath(lead.id)} className="text-ivory underline-offset-4 hover:underline">
        {unread ? <span className="sr-only">Unread: </span> : null}
        {lead.name}
      </Link>
      {lead.is_sample ? <Chip variant="sample">SAMPLE</Chip> : null}
      {lead.is_spam ? <Chip variant="archived">Spam</Chip> : null}
      {lead.duplicate_of ? <Chip variant="draft">Repeat enquiry</Chip> : null}
    </span>
  );
}

function LeadSourceCell({ lead }: { lead: Lead }) {
  const utm = [lead.utm?.source, lead.utm?.medium, lead.utm?.campaign].filter(Boolean).join(" / ");
  return (
    <span className="flex flex-col">
      <span>{LEAD_SOURCE[lead.source]}</span>
      {utm ? <span className="font-mono text-xs font-normal text-muted">{utm}</span> : null}
    </span>
  );
}

export function LeadsTable({ leads, busy, empty }: LeadsTableProps) {
  return (
    <section
      aria-label="Leads table"
      aria-busy={busy || undefined}
      className="overflow-hidden rounded-card border border-line bg-noir-800"
    >
      <Table
        caption="Leads, newest first"
        captionHidden
        columns={COLUMNS}
        rows={leads}
        rowKey={(lead) => lead.id}
        rowClassName={(lead) => (lead.read_at ? undefined : "font-bold text-ivory")}
        minWidth={980}
        busy={busy}
        empty={empty}
      />
    </section>
  );
}
