"use client";
/**
 * One lead (/admin/leads/[id], board NoirCmsLead): the summary with Call and WhatsApp, the stage,
 * the enquiry, the consent record, source and campaign, notes and the activity timeline, the
 * site visit, the duplicate check and, for a super-admin, "Erase personal data".
 *
 * How it works:
 *   1. The lead, its notes and its activity load in parallel. A lead this user may not see
 *      answers 404, exactly like one that doesn't exist (SECURITY.md §1), and says so.
 *   2. Opening an unread lead marks it read once (`POST …/read`), then the shell's dashboard
 *      counts refresh so the Leads badge goes down. "Mark unread" undoes it and returns to the
 *      inbox, through the unsaved-changes guard.
 *   3. Every change (stage, owner, spam, details, note, visit) refreshes the lead and its
 *      activity, so the timeline always shows what was just recorded.
 *   4. A typed note, open "Edit details", a chosen stage or an edited visit count as unsaved
 *      work: leaving by a link, signing out or closing the tab asks first (useUnsavedChanges).
 */
import Link from "next/link";
import { useCallback, useEffect, useRef } from "react";
import { Alert } from "@empire/ui";
import { api, call } from "@/lib/api";
import type { Lead, SiteVisit } from "@/lib/leads/labels";
import { isOpenVisit, visitDay } from "@/lib/leads/visits";
import { problemMessage, toProblem } from "@/lib/problems";
import { LEADS_PATH } from "@/lib/routes";
import { ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { useLoad } from "@/components/admin/useLoad";
import { useDirtyParts, useUnsavedChanges } from "@/components/admin/useUnsavedChanges";
import { useProjectOptions, useStaffOptions } from "@/components/admin/leads/useLeadOptions";
import { useAdminHeading, useAdminSession } from "../../session-context";
import { ConsentPanel, EnquiryPanel, SourcePanel } from "./LeadFacts";
import { DataRequestsPanel } from "./DataRequestsPanel";
import { RepeatsPanel, VisitPanel } from "./LeadSidebar";
import { LeadSummary } from "./LeadSummary";
import { LeadTimeline } from "./LeadTimeline";
import { StagePanel } from "./StagePanel";

export function LeadDetail({ id }: { id: string }) {
  const { can, dashboard } = useAdminSession();
  const lead = useLoad(`lead:${id}`, () =>
    call(api.GET("/api/v1/admin/leads/{id}", { params: { path: { id } } })),
  );
  const notes = useLoad(`lead-notes:${id}`, () =>
    call(api.GET("/api/v1/admin/leads/{id}/notes", { params: { path: { id } } })),
  );
  const activity = useLoad(`lead-activity:${id}`, () =>
    call(api.GET("/api/v1/admin/leads/{id}/activity", { params: { path: { id } } })),
  );
  // The lead's own visits (newest first) with `site_visits.manage`; otherwise the API's
  // `next_visit` on the lead is all this screen shows.
  const canManageVisits = can("site_visits.manage");
  const leadVisits = useLoad(`lead-visits:${id}:${canManageVisits}`, () =>
    canManageVisits
      ? call(api.GET("/api/v1/admin/site-visits", { params: { query: { lead_id: id } } }))
      : Promise.resolve(null),
  );
  const projects = useProjectOptions();
  const owners = useStaffOptions(can("leads.assign"));
  useAdminHeading(lead.data?.name ?? null);

  // Unsaved work anywhere on the page (a typed note, "Edit details", a chosen stage, the visit
  // form) makes leaving ask first, including "Mark unread", which goes back to the inbox.
  const { dirty, report } = useDirtyParts();
  const { dialog: leaveDialog, leave } = useUnsavedChanges(dirty);
  const noteDirty = useCallback((value: boolean) => report("note", value), [report]);
  const detailsDirty = useCallback((value: boolean) => report("details", value), [report]);
  const stageDirty = useCallback((value: boolean) => report("stage", value), [report]);
  const visitDirty = useCallback((value: boolean) => report("visit", value), [report]);

  // 2. Mark read once per visit to the page, only if it is unread.
  const markedRead = useRef(false);
  const refreshDashboard = dashboard?.refresh;
  const { refresh: refreshLead } = lead;
  const unread = lead.data ? !lead.data.read_at : false;
  useEffect(() => {
    if (!unread || markedRead.current) return;
    markedRead.current = true;
    void call(api.POST("/api/v1/admin/leads/{id}/read", { params: { path: { id } } }))
      .then(() => Promise.all([refreshLead(), refreshDashboard?.()]))
      .catch(() => {
        // WHY ignored: being marked read is a convenience; the lead is still shown, and the
        // next visit tries again.
        markedRead.current = false;
      });
  }, [unread, id, refreshLead, refreshDashboard]);

  if (lead.error) {
    if (toProblem(lead.error).status === 404) {
      return (
        <Alert tone="info" title="This lead isn't available.">
          It may not exist, or it belongs to someone else.{" "}
          <Link href={LEADS_PATH} className="font-bold underline">
            Back to leads
          </Link>
        </Alert>
      );
    }
    return (
      <ErrorPanel
        message={problemMessage(lead.error, "Couldn't load the lead.")}
        onRetry={lead.reload}
      />
    );
  }
  if (!lead.data) return <LoadingPanel label="Loading the lead…" rows={8} />;

  const current = lead.data;
  const canUpdate = can("leads.update") && !current.erased_at;
  const nameOf = (userId: string) => owners.find((o) => o.value === userId)?.label ?? null;

  async function refreshAll(saved?: Lead) {
    if (saved) lead.replace(saved);
    await Promise.all([
      saved ? Promise.resolve() : lead.refresh(),
      activity.refresh(),
      dashboard?.refresh(),
    ]).catch(() => undefined);
  }

  const visits = orderVisits(leadVisits.data ?? (current.next_visit ? [current.next_visit] : []));

  return (
    <>
      {current.is_sample ? (
        <p
          role="note"
          className="flex items-center gap-2.5 rounded-tile border border-line bg-noir-700 px-4 py-2.5 text-caption"
        >
          <span aria-hidden="true" className="size-2 shrink-0 rounded-pill bg-danger" />
          Sample data · this lead was made by the sample seed and is not a real person
        </p>
      ) : null}
      <LeadSummary
        lead={current}
        owners={owners}
        canAssign={can("leads.assign") && !current.erased_at}
        canUpdate={can("leads.update")}
        onSaved={(saved) => void refreshAll(saved)}
        onMarkUnread={async () => {
          // WHY first: the refresh below shows the lead unread, and this page must not then mark
          // it read again on its own (step 2 runs once per visit).
          markedRead.current = true;
          await call(api.POST("/api/v1/admin/leads/{id}/unread", { params: { path: { id } } }));
          await Promise.all([lead.refresh(), dashboard?.refresh()]).catch(() => undefined);
          // Through the guard: with unsaved work the user is asked, and "Stay" keeps them here.
          leave(LEADS_PATH);
        }}
      />
      {/* On a phone the panels stack; these jump to the work further down. */}
      <nav
        aria-label="On this page"
        className="flex flex-wrap gap-x-4 text-small font-bold xl:hidden"
      >
        <a href="#activity-title" className="inline-flex min-h-11 items-center">
          Notes and activity
        </a>
        <a href="#visit-title" className="inline-flex min-h-11 items-center">
          Site visit
        </a>
      </nav>
      <StagePanel
        onDirtyChange={stageDirty}
        key={current.id}
        lead={current}
        canUpdate={canUpdate}
        onSaved={(saved) => void refreshAll(saved)}
      />
      <div className="grid items-start gap-4 lg:grid-cols-2 xl:grid-cols-[minmax(280px,320px)_minmax(0,1fr)_minmax(280px,300px)]">
        <div className="flex min-w-0 flex-col gap-4">
          <EnquiryPanel
            onDirtyChange={detailsDirty}
            lead={current}
            canUpdate={canUpdate}
            projects={projects}
            onSaved={(saved) => void refreshAll(saved)}
          />
          <ConsentPanel lead={current} />
          <SourcePanel lead={current} />
        </div>
        <LeadTimeline
          onDirtyChange={noteDirty}
          leadId={id}
          notes={notes.data}
          activity={activity.data}
          error={notes.error ?? activity.error}
          onRetry={() => {
            notes.reload();
            activity.reload();
          }}
          canAddNote={canUpdate}
          nameOf={nameOf}
          onNoteAdded={async () => {
            await Promise.all([notes.refresh(), activity.refresh()]).catch(() => undefined);
          }}
        />
        <div className="flex min-w-0 flex-col gap-4">
          <VisitPanel
            onDirtyChange={visitDirty}
            visits={visits}
            staff={owners}
            canManage={canManageVisits && !current.erased_at}
            onSaved={() => {
              void Promise.all([refreshAll(), leadVisits.refresh()]).catch(() => undefined);
            }}
          />
          <RepeatsPanel lead={current} seesAll={can("leads.read_all")} />
          {can("leads.erase") ? (
            <DataRequestsPanel
              lead={current}
              onErased={() => {
                void Promise.all([refreshAll(), notes.refresh()]).catch(() => undefined);
              }}
            />
          ) : null}
        </div>
      </div>
      {leaveDialog}
    </>
  );
}

/** Open visits first (the soonest), then the rest, newest first: the panel acts on the first. */
function orderVisits(visits: SiteVisit[]): SiteVisit[] {
  const open = visits
    .filter(isOpenVisit)
    .sort((a, b) => (visitDay(a) ?? "").localeCompare(visitDay(b) ?? ""));
  const closed = visits
    .filter((visit) => !isOpenVisit(visit))
    .sort((a, b) => (visitDay(b) ?? "").localeCompare(visitDay(a) ?? ""));
  return [...open, ...closed];
}
