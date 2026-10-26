"use client";
/**
 * The inbox as a pipeline board (board NoirCmsLeads, "Board" view): one column per stage, newest
 * leads first, up to 20 cards per column with a link to the rest.
 *
 * Moving a lead uses a real "Move to" list on each card, so it works with a keyboard, a screen
 * reader and a phone; dragging is not offered (WCAG 2.1.1, the boards' "drag is optional").
 * Moving to Lost asks for the reason first. Every move is announced in a polite live region and
 * recorded in the lead's activity by the API.
 *
 * How it works:
 *   1. One request per stage with the inbox filters (the stage is the column), in parallel; each
 *      answer's `meta.total` is the column count.
 *   2. A move PATCHes the lead's status, then reloads the columns quietly and puts focus back on
 *      the moved card's "Move to" list in its new column, so keyboard users keep their place.
 */
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Alert, Button, Chip, Dialog, LiveRegion, Select, cx } from "@empire/ui";
import { formatAge } from "@empire/ui/format";
import { api, call } from "@/lib/api";
import { updateLead } from "@/lib/leads/api";
import { leadsHref, leadsQuery, type LeadFilters } from "@/lib/leads/filters";
import {
  LEAD_SOURCE,
  LEAD_STATUS,
  LEAD_STATUS_ORDER,
  lostReasonLabel,
  type Lead,
  type LeadStatus,
} from "@/lib/leads/labels";
import { problemMessage } from "@/lib/problems";
import { leadPath } from "@/lib/routes";
import { ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { useLoad } from "@/components/admin/useLoad";
import {
  EMPTY_REASON,
  LostReasonFields,
  lostReasonBody,
  lostReasonError,
  type LostReasonValue,
} from "@/components/admin/leads/LostReasonFields";

type LostReasonBody = NonNullable<ReturnType<typeof lostReasonBody>>;
import { initials } from "@/lib/leads/people";

const PER_COLUMN = 20;

// Column accents from the board (a 2 px bar under each heading); text colours are the stage tokens.
const BAR: Record<LeadStatus, string> = {
  new: "bg-gold-500",
  contacted: "bg-stage-contacted-border",
  site_visit: "bg-palm-line",
  negotiation: "bg-gold-700",
  booked: "bg-stage-booked-text",
  lost: "bg-danger",
};
const HEADING: Record<LeadStatus, string> = {
  new: "text-stage-new-text",
  contacted: "text-stage-contacted-text",
  site_visit: "text-stage-site-visit-text",
  negotiation: "text-stage-negotiation-text",
  booked: "text-stage-booked-text",
  lost: "text-stage-lost-text",
};

interface Column {
  status: LeadStatus;
  leads: Lead[];
  total: number;
}

export interface LeadsBoardProps {
  filters: LeadFilters;
  /** With `leads.update` the cards offer "Move to". */
  canMove: boolean;
}

export function LeadsBoard({ filters, canMove }: LeadsBoardProps) {
  const board = useLoad(`board:${leadsHref({ ...filters, page: 1 })}`, () =>
    Promise.all(
      LEAD_STATUS_ORDER.map(async (status): Promise<Column> => {
        const page = await call(
          api.GET("/api/v1/admin/leads", {
            params: { query: { ...leadsQuery({ ...filters, status }, 1, PER_COLUMN) } },
          }),
        );
        return { status, leads: page.items, total: page.meta.total };
      }),
    ),
  );
  const [announcement, setAnnouncement] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [losing, setLosing] = useState<Lead | null>(null);
  const focusAfterLoad = useRef<string | null>(null);

  useEffect(() => {
    const id = focusAfterLoad.current;
    if (!id || !board.data) return;
    focusAfterLoad.current = null;
    document.querySelector<HTMLSelectElement>(`[data-move-lead="${id}"]`)?.focus();
  }, [board.data]);

  async function move(lead: Lead, status: LeadStatus, lostReason: LostReasonBody | null = null) {
    setSavingId(lead.id);
    setError(null);
    try {
      await updateLead(
        lead.id,
        status === "lost" && lostReason ? { status, ...lostReason } : { status },
      );
    } catch (err) {
      setError(problemMessage(err, `Couldn't move ${lead.name}.`));
      setSavingId(null);
      return false;
    }
    setAnnouncement(`${lead.name} moved to ${LEAD_STATUS[status]}.`);
    focusAfterLoad.current = lead.id;
    await board.refresh().catch(() => undefined);
    setSavingId(null);
    return true;
  }

  if (board.error) {
    return (
      <ErrorPanel
        message={problemMessage(board.error, "Couldn't load the pipeline.")}
        onRetry={board.reload}
      />
    );
  }
  if (!board.data) return <LoadingPanel label="Loading the pipeline…" rows={6} />;

  return (
    <>
      <LiveRegion message={announcement} />
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="@container">
        <div
          aria-busy={board.loading || undefined}
          className="grid grid-cols-1 items-start gap-2.5 @xl:grid-cols-2 @3xl:grid-cols-3 @5xl:grid-cols-6"
        >
          {board.data.map((column) => (
            <BoardColumn
              key={column.status}
              column={column}
              filters={filters}
              canMove={canMove}
              savingId={savingId}
              onMove={(lead, status) =>
                status === "lost" ? setLosing(lead) : void move(lead, status)
              }
            />
          ))}
        </div>
      </div>
      <p className="text-caption text-muted">
        Use &quot;Move to&quot; on a card to change its stage. Moving to Lost asks for a reason.
        Every move is recorded in the lead&apos;s activity.
      </p>
      <LostDialog
        // WHY the key: a fresh dialog (no reason left over) for every lead.
        key={losing?.id ?? "none"}
        lead={losing}
        onCancel={() => setLosing(null)}
        onConfirm={async (reason) => {
          if (!losing) return;
          if (await move(losing, "lost", reason)) setLosing(null);
        }}
        busy={savingId !== null}
      />
    </>
  );
}

function BoardColumn({
  column,
  filters,
  canMove,
  savingId,
  onMove,
}: {
  column: Column;
  filters: LeadFilters;
  canMove: boolean;
  savingId: string | null;
  onMove: (lead: Lead, status: LeadStatus) => void;
}) {
  const label = LEAD_STATUS[column.status];
  const more = column.total - column.leads.length;
  const headingId = `board-${column.status}`;
  return (
    <section
      aria-labelledby={headingId}
      className="flex min-w-0 flex-col gap-2 rounded-tile border border-line bg-noir-800 p-2.5"
    >
      <div className="flex items-center justify-between gap-1.5 px-1 pt-0.5">
        <h2
          id={headingId}
          className={cx("text-caption font-extrabold tracking-[0.04em]", HEADING[column.status])}
        >
          {label}
          <span className="sr-only">
            : {column.total} {column.total === 1 ? "lead" : "leads"}
          </span>
        </h2>
        <span
          aria-hidden="true"
          className="rounded-pill border border-line-strong bg-noir-700 px-2 text-xs font-extrabold text-ivory tabular-nums"
        >
          {column.total}
        </span>
      </div>
      <span aria-hidden="true" className={cx("h-0.5 rounded-pill", BAR[column.status])} />
      {column.leads.length === 0 ? (
        <p className="px-1 py-2 text-caption text-muted">No leads at this stage.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {column.leads.map((lead) => (
            <li key={lead.id}>
              <LeadCard
                lead={lead}
                canMove={canMove}
                saving={savingId === lead.id}
                onMove={(status) => onMove(lead, status)}
              />
            </li>
          ))}
        </ul>
      )}
      {more > 0 ? (
        <Link
          href={leadsHref({ ...filters, view: "table", status: column.status, page: 1 })}
          className="inline-flex min-h-11 items-center px-1 text-caption font-bold"
        >
          + {more} more in {label}
        </Link>
      ) : null}
    </section>
  );
}

function LeadCard({
  lead,
  canMove,
  saving,
  onMove,
}: {
  lead: Lead;
  canMove: boolean;
  saving: boolean;
  onMove: (status: LeadStatus) => void;
}) {
  const unread = !lead.read_at;
  const owner = lead.owner?.name ?? "Unassigned";
  return (
    <article
      aria-label={lead.name}
      className="flex flex-col gap-1.5 rounded-tile border border-line bg-noir-700 p-2.5"
    >
      <div className="flex items-baseline justify-between gap-1.5">
        <span className="flex min-w-0 items-baseline gap-1.5">
          {unread ? (
            <span
              aria-hidden="true"
              className="size-2 shrink-0 self-center rounded-pill bg-gold-500"
            />
          ) : null}
          <Link
            href={leadPath(lead.id)}
            className={cx(
              "text-small [overflow-wrap:anywhere] text-ivory",
              unread ? "font-extrabold" : "font-bold",
            )}
          >
            {unread ? <span className="sr-only">Unread: </span> : null}
            {lead.name}
          </Link>
        </span>
        <time dateTime={lead.created_at} className="shrink-0 text-xs text-muted">
          {formatAge(lead.created_at)}
        </time>
      </div>
      <span className="text-caption">{lead.project?.name ?? "General enquiry"}</span>
      {lead.is_sample ? (
        <Chip variant="sample" className="self-start">
          SAMPLE
        </Chip>
      ) : null}
      {lead.status === "lost" && lead.lost_reason ? (
        <span className="text-xs text-stage-lost-text">Reason: {lostReasonLabel(lead)}</span>
      ) : null}
      <div className="flex items-center justify-between gap-1.5">
        <span className="truncate rounded-pill border border-line-strong px-2 text-xs font-bold">
          {LEAD_SOURCE[lead.source]}
        </span>
        <span
          title={`Owner: ${owner}`}
          className="flex size-6.5 shrink-0 items-center justify-center rounded-pill border border-line-strong bg-noir-900 text-[10.5px] font-extrabold text-gold-300"
        >
          <span aria-hidden="true">{lead.owner ? initials(lead.owner.name) : "–"}</span>
          <span className="sr-only">Owner: {owner}</span>
        </span>
      </div>
      {canMove ? (
        <Select
          label={
            <span className="text-xs">
              Move to<span className="sr-only">, {lead.name}</span>
            </span>
          }
          data-move-lead={lead.id}
          value={lead.status}
          disabled={saving}
          options={LEAD_STATUS_ORDER.map((status) => ({
            value: status,
            label: LEAD_STATUS[status],
          }))}
          onChange={(event) => {
            const next = event.target.value as LeadStatus;
            if (next !== lead.status) onMove(next);
          }}
        />
      ) : null}
    </article>
  );
}

function LostDialog({
  lead,
  busy,
  onCancel,
  onConfirm,
}: {
  lead: Lead | null;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (reason: LostReasonBody) => void;
}) {
  const [reason, setReason] = useState<LostReasonValue>(EMPTY_REASON);
  const [error, setError] = useState<string | null>(null);
  return (
    <Dialog
      open={lead !== null}
      title={lead ? `Mark ${lead.name} as lost?` : "Mark as lost?"}
      busy={busy}
      onClose={onCancel}
      onSubmit={() => {
        const body = lostReasonBody(reason);
        if (!body) {
          setError(lostReasonError(reason));
          return;
        }
        setError(null);
        onConfirm(body);
      }}
      footer={
        <>
          <Button variant="secondary" disabled={busy} onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" loading={busy}>
            Mark lost
          </Button>
        </>
      }
    >
      <p className="text-small">
        The move is recorded in the lead&apos;s activity. You can move it back later if they come
        back.
      </p>
      <LostReasonFields idPrefix="board-lost" value={reason} onChange={setReason} error={error} />
    </Dialog>
  );
}
