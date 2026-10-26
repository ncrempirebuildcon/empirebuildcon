"use client";
/**
 * The right-hand column of the lead detail (board NoirCmsLead): the lead's site visit and repeat
 * enquiries (the duplicate check). "Data requests" lives in DataRequestsPanel.tsx.
 *
 * - Site visit: the next open visit, confirmed and rescheduled inline (VisitEditor) with
 *   `site_visits.manage`, with a link to it on the calendar.
 * - Repeat enquiries: the same mobile and project within 24 hours creates a linked lead without
 *   a second alert (ARCHITECTURE §8); both ends of the link are shown when the viewer may open them.
 */
import Link from "next/link";
import { useState } from "react";
import { LiveRegion, type SelectOption } from "@empire/ui";
import { formatDateTime } from "@/lib/dates";
import type { Lead, SiteVisit } from "@/lib/leads/labels";
import { visitDay, visitWhen } from "@/lib/leads/visits";
import { SITE_VISITS_PATH, leadPath } from "@/lib/routes";
import { Panel } from "@/components/admin/states";
import { DayTile } from "@/components/admin/leads/DayTile";
import { VisitEditor } from "@/components/admin/leads/VisitEditor";

export function VisitPanel({
  visits,
  staff,
  canManage,
  onSaved,
  onDirtyChange,
}: {
  /** The lead's visits, newest first; the open ones are shown for action. */
  visits: SiteVisit[];
  staff: SelectOption[];
  canManage: boolean;
  onSaved: () => void;
  /** Whether the visit form holds changes not saved yet (for the leave warning). */
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [shown, ...older] = visits;
  const [announcement, setAnnouncement] = useState("");
  return (
    <Panel id="visit" title="Site visit">
      <LiveRegion message={announcement} />
      {!shown ? (
        <p className="text-small">
          No site visit yet. When the buyer asks for one on the website it appears here and on the
          calendar.
        </p>
      ) : (
        <>
          <div className="flex items-center gap-3">
            {visitDay(shown) ? <DayTile date={visitDay(shown) as string} /> : null}
            <span className="flex flex-col text-small">
              <strong className="text-ivory">{visitWhen(shown)}</strong>
              <span>{shown.project.name}</span>
            </span>
          </div>
          <VisitEditor
            key={shown.id}
            visit={shown}
            staff={staff}
            canManage={canManage}
            idPrefix="lead-visit"
            onSaved={onSaved}
            onAnnounce={setAnnouncement}
            onDirtyChange={onDirtyChange}
          />
          {older.length > 0 ? (
            <details className="text-small">
              <summary className="min-h-11 cursor-pointer py-2 font-bold text-gold-400">
                Earlier visits ({older.length})
              </summary>
              <ul className="flex flex-col gap-1.5">
                {older.map((visit) => (
                  <li key={visit.id}>
                    {visitWhen(visit)} · {visit.project.name} · {visit.status.replace("_", "-")}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </>
      )}
      {canManage ? (
        <Link
          href={
            shown
              ? `${SITE_VISITS_PATH}?date=${visitDay(shown) ?? ""}&visit=${shown.id}`
              : SITE_VISITS_PATH
          }
          className="inline-flex min-h-11 items-center text-caption font-bold"
        >
          Open the calendar
        </Link>
      ) : null}
    </Panel>
  );
}

/**
 * The duplicate check. SECURITY (SECURITY.md §1): the API leaves out the original and any
 * repeats this viewer may not open, so nothing here names or links a lead they can't see, and
 * with nothing to show a viewer without `leads.read_all` gets a sentence that claims nothing
 * about leads outside their own.
 */
export function RepeatsPanel({ lead, seesAll }: { lead: Lead; seesAll: boolean }) {
  const repeats = lead.duplicates ?? [];
  const original =
    lead.duplicate_of && lead.duplicate_of_reference
      ? { id: lead.duplicate_of, reference: lead.duplicate_of_reference }
      : null;
  return (
    <Panel id="repeats" title="Duplicate check">
      {original ? (
        <p className="text-small">
          A repeat enquiry: the same mobile asked about the same project within 24 hours, so no
          second alert went out. First enquiry:{" "}
          <Link href={leadPath(original.id)} className="font-bold">
            {original.reference}
          </Link>
          .
        </p>
      ) : null}
      {repeats.length > 0 ? (
        <div className="flex flex-col gap-1.5 text-small">
          <p>
            {repeats.length === 1
              ? "A later enquiry was"
              : `${repeats.length} later enquiries were`}{" "}
            linked to this lead instead of alerting again:
          </p>
          <ul className="flex flex-col gap-1">
            {repeats.map((repeat) => (
              <li key={repeat.id}>
                <Link href={leadPath(repeat.id)} className="font-bold">
                  {repeat.reference}
                </Link>{" "}
                <span className="text-muted">· {formatDateTime(repeat.created_at)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {!original && repeats.length === 0 ? (
        <p className="flex items-start gap-2 text-small">
          <span aria-hidden="true" className="font-extrabold text-palm">
            ✓
          </span>
          {seesAll
            ? "No repeat enquiries linked to this lead."
            : "No repeat enquiries linked among the leads you can open."}
        </p>
      ) : null}
    </Panel>
  );
}
