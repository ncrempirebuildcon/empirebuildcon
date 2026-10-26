"use client";
/**
 * CMS dashboard (board NoirCmsDashboard): "At a glance" count tiles that open the filtered lists,
 * the latest leads, "Needs attention" tasks, the upcoming site visits and, with `leads.report`,
 * leads by source for the last 30 days.
 *
 * The data is the shell's single `GET /admin/dashboard` (useAdminSession().dashboard), which also
 * feeds the Leads badge. Counts, links, latest leads and visits are worked out by the API with the
 * object-level rule: a sales user's tiles and lists cover only their own leads (SECURITY.md §1).
 *
 * Honest empty states: when there is nothing to show, each panel says so and what happens next,
 * never a placeholder number.
 * SECURITY: links in the answer (counts and tasks) are followed only when they stay inside the
 * CMS and lead to a screen that exists (`isBuiltCmsPath`); a task for a screen still to come
 * (Settings, part 5) is shown without a link.
 */
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { Button, Chip, Table, buttonClasses, maskPhone, type TableColumn } from "@empire/ui";
import { formatAge } from "@empire/ui/format";
import type { Schema } from "@/lib/api";
import { countAction } from "@/lib/leads/dashboard";
import {
  LEAD_SOURCE,
  VISIT_STATUS_CHIP,
  VISIT_STATUS_SHORT,
  type Lead,
  type SiteVisit,
} from "@/lib/leads/labels";
import { visitDay, visitWhen } from "@/lib/leads/visits";
import { problemMessage } from "@/lib/problems";
import {
  LEADS_PATH,
  PROJECTS_PATH,
  SITE_VISITS_PATH,
  isBuiltCmsPath,
  leadPath,
} from "@/lib/routes";
import { EmptyState, ErrorPanel, LoadingPanel, Panel } from "@/components/admin/states";
import { DayTile } from "@/components/admin/leads/DayTile";
import { LeadsBySource } from "@/components/admin/leads/LeadsBySource";
import { StageChip } from "@/components/admin/leads/StageChip";
import { useAdminSession } from "./session-context";

type Dashboard = Schema<"Dashboard">;
type Task = NonNullable<Dashboard["tasks"]>[number];
type Count = NonNullable<Dashboard["counts"]>[number];

export function DashboardHome() {
  const { me, can, dashboard } = useAdminSession();

  if (!dashboard) {
    return (
      <Panel title={`Welcome, ${me.name}`}>
        <p className="max-w-[60ch]">Use the menu to open the screens your role can use.</p>
      </Panel>
    );
  }
  if (dashboard.error) {
    return (
      <ErrorPanel
        message={problemMessage(dashboard.error, "Couldn't load the dashboard.")}
        onRetry={dashboard.reload}
      />
    );
  }
  if (!dashboard.data) return <LoadingPanel label="Loading the dashboard…" rows={6} />;

  const data = dashboard.data;
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-[17px] font-bold">At a glance</h2>
        <div className="flex flex-wrap gap-2.5">
          {can("leads.update") ? (
            <Link href={`${LEADS_PATH}?add=1`} className={buttonClasses("secondary")}>
              + Add lead
            </Link>
          ) : null}
          {can("projects.write") ? (
            <Link href={`${PROJECTS_PATH}/new`} className={buttonClasses("primary")}>
              + New project
            </Link>
          ) : null}
        </div>
      </div>

      <CountTiles counts={data.counts ?? []} />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)] lg:items-start">
        <div className="flex min-w-0 flex-col gap-5">
          {can("leads.read") ? (
            <LatestLeads leads={data.latest_leads ?? []} seesAll={can("leads.read_all")} />
          ) : null}
          {can("leads.read") || can("leads.report") ? (
            <LeadsBySource rows={data.leads_by_source} canOpenReport={can("leads.report")} />
          ) : null}
        </div>
        <div className="flex min-w-0 flex-col gap-5">
          <Tasks tasks={data.tasks ?? []} />
          {can("site_visits.manage") ? (
            <UpcomingVisits visits={data.upcoming_visits ?? []} seesAll={can("leads.read_all")} />
          ) : null}
        </div>
      </div>
    </>
  );
}

function CountTiles({ counts }: { counts: Count[] }) {
  if (counts.length === 0) {
    return (
      <p className="rounded-card border border-line bg-noir-800 p-4.5 text-small">
        There are no counts for your role.
      </p>
    );
  }
  return (
    <ul
      aria-label="Counts"
      className="grid grid-cols-[repeat(auto-fill,minmax(170px,1fr))] gap-3.5"
    >
      {counts.map((count) => (
        <li key={count.key} className="flex">
          <TileLink link={count.link}>
            <span className="text-caption font-bold text-body">{count.label}</span>
            <strong className="font-display text-[36px] leading-[1.1] font-semibold text-gold-300 tabular-nums">
              {count.count}
            </strong>
            {isBuiltCmsPath(count.link) ? (
              <span className="text-caption font-bold text-gold-400">
                {countAction(count.key)} <span aria-hidden="true">→</span>
              </span>
            ) : null}
          </TileLink>
        </li>
      ))}
    </ul>
  );
}

/** A count tile: a link when the API's link stays inside the CMS, plain text otherwise. */
function TileLink({ link, children }: { link: string; children: ReactNode }) {
  const classes =
    "flex w-full flex-col gap-1 rounded-card border border-line bg-noir-800 px-4.5 py-4 text-body no-underline hover:border-gold-line-strong hover:text-body";
  return isBuiltCmsPath(link) ? (
    <Link href={link} className={classes}>
      {children}
    </Link>
  ) : (
    <div className={classes}>{children}</div>
  );
}

const LEAD_COLUMNS: TableColumn<Lead>[] = [
  {
    key: "name",
    header: "Name",
    rowHeader: true,
    cell: (lead) => (
      <span className="flex flex-col">
        <span className="flex flex-wrap items-center gap-2">
          <Link href={leadPath(lead.id)} className="text-ivory">
            {lead.read_at ? null : <span className="sr-only">Unread: </span>}
            {lead.name}
          </Link>
          {lead.is_sample ? <Chip variant="sample">SAMPLE</Chip> : null}
        </span>
        <span className="text-xs font-normal text-muted tabular-nums">
          {maskPhone(lead.phone_e164)}
        </span>
      </span>
    ),
  },
  {
    key: "project",
    header: "Project",
    cell: (lead) => lead.project?.name ?? <span className="text-muted">General enquiry</span>,
  },
  { key: "source", header: "Source", cell: (lead) => LEAD_SOURCE[lead.source] },
  { key: "stage", header: "Stage", cell: (lead) => <StageChip status={lead.status} /> },
  {
    key: "owner",
    header: "Owner",
    cell: (lead) => lead.owner?.name ?? <span className="text-muted">Unassigned</span>,
  },
  {
    key: "received",
    header: "Received",
    className: "whitespace-nowrap text-muted",
    cell: (lead) => {
      const age = formatAge(lead.created_at);
      return <time dateTime={lead.created_at}>{age === "just now" ? age : `${age} ago`}</time>;
    },
  },
];

/** `seesAll`: with `leads.read_all` the lists cover every lead, else only the user's own. */
function LatestLeads({ leads, seesAll }: { leads: Lead[]; seesAll: boolean }) {
  return (
    <Panel
      id="latest-leads"
      title="Latest leads"
      actions={
        <Link href={LEADS_PATH} className="inline-flex min-h-11 items-center font-bold">
          Open all leads
        </Link>
      }
    >
      <div className="-mx-4.5 -mb-4.5 border-t border-line">
        <Table
          caption="Latest leads"
          captionHidden
          columns={LEAD_COLUMNS}
          rows={leads}
          rowKey={(lead) => lead.id}
          rowClassName={(lead) => (lead.read_at ? undefined : "font-bold text-ivory")}
          minWidth={640}
          empty={
            <EmptyState title="No leads yet.">
              <p className="text-small">
                {seesAll
                  ? "New enquiries from the website appear here as soon as they arrive."
                  : "Leads given to you appear here as soon as they are assigned."}
              </p>
            </EmptyState>
          }
        />
      </div>
    </Panel>
  );
}

/** How many tasks show before "Show all": the board shows a short list. */
const TASKS_SHOWN = 5;

function Tasks({ tasks }: { tasks: Task[] }) {
  const [all, setAll] = useState(false);
  const shown = all ? tasks : tasks.slice(0, TASKS_SHOWN);
  return (
    <Panel id="attention" title="Needs attention">
      {tasks.length === 0 ? (
        <p className="text-small">Nothing needs attention right now.</p>
      ) : (
        <>
          <ul id="attention-list" className="flex flex-col gap-2.5">
            {shown.map((task, index) => (
              <li key={`${task.key}-${index}`}>
                <TaskItem task={task} />
              </li>
            ))}
          </ul>
          {tasks.length > TASKS_SHOWN ? (
            <Button
              variant="tertiary"
              className="min-h-11 self-start"
              aria-expanded={all}
              aria-controls="attention-list"
              onClick={() => setAll((open) => !open)}
            >
              {all ? "Show fewer" : `Show all ${tasks.length}`}
            </Button>
          ) : null}
        </>
      )}
    </Panel>
  );
}

function TaskItem({ task }: { task: Task }) {
  const body = (
    <>
      <span aria-hidden="true" className="mt-1.5 size-2.5 shrink-0 rounded-pill bg-gold-500" />
      <span className="flex flex-col gap-0.5 text-small">
        <strong className="text-ivory">{task.label}</strong>
        {task.detail ? <span>{task.detail}</span> : null}
        {isBuiltCmsPath(task.link) ? (
          <span className="text-caption font-bold text-gold-400">
            Open <span aria-hidden="true">→</span>
          </span>
        ) : (
          <span className="text-caption text-muted">Its screen arrives in a later update.</span>
        )}
      </span>
    </>
  );
  const classes =
    "flex min-h-11 items-start gap-3 rounded-tile border border-line bg-noir-700 p-3 text-body no-underline";
  return isBuiltCmsPath(task.link) ? (
    <Link href={task.link} className={`${classes} hover:border-gold-line-strong hover:text-body`}>
      {body}
    </Link>
  ) : (
    <div className={classes}>{body}</div>
  );
}

function UpcomingVisits({ visits, seesAll }: { visits: SiteVisit[]; seesAll: boolean }) {
  return (
    <Panel
      id="upcoming-visits"
      title="Upcoming site visits"
      actions={
        <Link href={SITE_VISITS_PATH} className="inline-flex min-h-11 items-center font-bold">
          Calendar
        </Link>
      }
    >
      {visits.length === 0 ? (
        <p className="text-small">
          No site visits coming up.{" "}
          {seesAll
            ? "Requests from the website appear here for you to confirm."
            : "Requests from your leads appear here for you to confirm."}
        </p>
      ) : (
        <ul className="flex flex-col">
          {visits.map((visit) => {
            const day = visitDay(visit);
            return (
              <li key={visit.id} className="flex items-center gap-3 border-t border-line py-2.5">
                {day ? <DayTile date={day} /> : null}
                <span className="flex min-w-0 flex-1 flex-col text-small">
                  <Link
                    href={`${SITE_VISITS_PATH}?${new URLSearchParams({ date: day ?? "", visit: visit.id })}`}
                    className="font-bold text-ivory"
                  >
                    {visit.lead_name}
                  </Link>
                  <span>
                    {visit.project.name} · {visitWhen(visit)}
                  </span>
                </span>
                <Chip variant={VISIT_STATUS_CHIP[visit.status]} className="whitespace-nowrap">
                  {visit.status === "requested" ? "To confirm" : VISIT_STATUS_SHORT[visit.status]}
                </Chip>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
