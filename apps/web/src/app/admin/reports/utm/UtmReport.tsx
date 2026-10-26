"use client";
/**
 * The UTM report (/admin/reports/utm, `leads.report`): how many leads each campaign brought, how
 * many of them asked for a site visit and how many booked, for a date range. Counts only.
 *
 * The range, the grouping and nothing else live in the address (`?from=&to=&group_by=`); the
 * default is the last 30 days in India time, grouped by source, medium, campaign and project.
 *
 * COMPLIANCE / SECURITY: no personal data appears here or in the API's answer (SECURITY.md §8);
 * marketing can read it without seeing a single lead. A sales user's counts cover only their own
 * leads (the API applies the object-level rule). With `leads.read`, a row's lead count links to
 * the inbox filtered by every column of that row (`rowLeadsHref`), where the usual rules apply.
 */
import Link from "next/link";
import { useMemo, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, Select, Table, TextField, type TableColumn } from "@empire/ui";
import { addDays, isCalendarDate, istToday } from "@empire/ui/format";
import { api, call, type Schema } from "@/lib/api";
import { formatCalendarDate } from "@/lib/dates";
import { EMPTY_FILTERS, GENERAL, leadsHref } from "@/lib/leads/filters";
import { problemMessage } from "@/lib/problems";
import { UTM_REPORT_PATH, projectPath } from "@/lib/routes";
import { EmptyState, ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { useLoad } from "@/components/admin/useLoad";
import { useAdminSession } from "../../session-context";

type Row = Schema<"UtmReportRow">;
type Group = "source" | "medium" | "campaign" | "project";

const GROUPS: Record<Group, string> = {
  source: "Source",
  medium: "Medium",
  campaign: "Campaign",
  project: "Project",
};

interface ReportState {
  from: string;
  to: string;
  group: Group | "";
}

function readState(params: URLSearchParams): ReportState {
  const today = istToday();
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";
  const group = params.get("group_by") ?? "";
  return {
    from: isCalendarDate(from) ? from : addDays(today, -29),
    to: isCalendarDate(to) ? to : today,
    group: Object.hasOwn(GROUPS, group) ? (group as Group) : "",
  };
}

function reportHref(state: ReportState): string {
  const search = new URLSearchParams({ from: state.from, to: state.to });
  if (state.group) search.set("group_by", state.group);
  return `${UTM_REPORT_PATH}?${search.toString()}`;
}

const blank = <span className="text-muted">(none)</span>;

export function UtmReport() {
  const params = useSearchParams();
  const router = useRouter();
  const { can } = useAdminSession();
  const state = useMemo(() => readState(params), [params]);
  const report = useLoad(reportHref(state), () =>
    call(
      api.GET("/api/v1/admin/reports/utm", {
        params: {
          query: { from: state.from, to: state.to, group_by: state.group || undefined },
        },
      }),
    ),
  );

  const rows = report.data ?? [];
  const totals = rows.reduce(
    (sum, row) => ({
      leads: sum.leads + row.leads,
      visits: sum.visits + row.site_visits,
      booked: sum.booked + row.booked,
    }),
    { leads: 0, visits: 0, booked: 0 },
  );
  const shownGroups: Group[] = state.group
    ? [state.group]
    : ["source", "medium", "campaign", "project"];
  const columns = reportColumns(shownGroups, state, can("leads.read"));

  return (
    <>
      <p className="max-w-[70ch] text-small text-muted">
        Leads by campaign tags (UTM), with how many asked for a site visit and how many booked.
        Counts only: no names or numbers are shown or sent here.
      </p>
      <RangeForm
        key={`${state.from}|${state.to}|${state.group}`}
        state={state}
        onApply={(next) => router.replace(reportHref(next), { scroll: false })}
      />
      {report.error ? (
        <ErrorPanel
          message={problemMessage(report.error, "Couldn't load the report.")}
          onRetry={report.reload}
        />
      ) : !report.data ? (
        <LoadingPanel label="Loading the report…" rows={5} />
      ) : (
        <>
          <p role="status" className="text-small">
            {formatCalendarDate(state.from)} – {formatCalendarDate(state.to)}:{" "}
            <strong className="text-ivory">
              {totals.leads} {totals.leads === 1 ? "lead" : "leads"}
            </strong>{" "}
            · {totals.visits} asked for a site visit · {totals.booked} booked
          </p>
          <section
            aria-busy={report.loading || undefined}
            className="overflow-hidden rounded-card border border-line bg-noir-800"
          >
            <Table
              caption={`Leads by ${shownGroups.map((g) => GROUPS[g].toLowerCase()).join(", ")}`}
              columns={columns}
              rows={rows}
              rowKey={(row) =>
                [row.source, row.medium, row.campaign, row.project_id ?? row.project].join("|")
              }
              minWidth={shownGroups.length > 1 ? 820 : 480}
              busy={report.loading}
              empty={
                <EmptyState title="No leads in these dates.">
                  <p className="text-small">Try a longer date range.</p>
                </EmptyState>
              }
            />
          </section>
        </>
      )}
    </>
  );
}

/**
 * The inbox address that lists exactly the leads counted in `row`: every grouped column becomes
 * its filter (`utm_source`, `utm_medium`, `utm_campaign`, `project_id` or "none"), plus the dates.
 * Null when a grouped tag is empty: the inbox can't filter on "no tag", so a link would open more
 * leads than the row counts. SECURITY: the inbox applies the usual lead rules (SECURITY.md §1).
 */
function rowLeadsHref(row: Row, groups: Group[], state: ReportState): string | null {
  const filters = { ...EMPTY_FILTERS, from: state.from, to: state.to };
  for (const group of groups) {
    if (group === "project") {
      filters.project_id = row.project_id ?? GENERAL;
      continue;
    }
    const value = row[group];
    if (!value) return null;
    filters[
      group === "source" ? "utm_source" : group === "medium" ? "utm_medium" : "utm_campaign"
    ] = value;
  }
  return leadsHref(filters);
}

function reportColumns(
  groups: Group[],
  state: ReportState,
  canOpenLeads: boolean,
): TableColumn<Row>[] {
  const dimension: Record<Group, TableColumn<Row>> = {
    source: { key: "source", header: "Source", cell: (row) => row.source ?? blank },
    medium: { key: "medium", header: "Medium", cell: (row) => row.medium ?? blank },
    campaign: {
      key: "campaign",
      header: "Campaign",
      className: "font-mono text-caption",
      cell: (row) => row.campaign ?? blank,
    },
    project: {
      key: "project",
      header: "Project",
      cell: (row) =>
        row.project_id && row.project ? (
          <Link href={projectPath(row.project_id)}>{row.project}</Link>
        ) : (
          (row.project ?? <span className="text-muted">General enquiries</span>)
        ),
    },
  };
  const count = (key: "leads" | "site_visits" | "booked", header: string): TableColumn<Row> => ({
    key,
    header,
    className: "text-right tabular-nums",
    headerClassName: "text-right",
    cell: (row) => row[key],
  });
  const leads: TableColumn<Row> = {
    ...count("leads", "Leads"),
    cell: (row) => {
      const href = canOpenLeads ? rowLeadsHref(row, groups, state) : null;
      return href ? (
        <Link href={href} className="font-bold">
          {row.leads}
          <span className="sr-only"> {row.leads === 1 ? "lead" : "leads"}: open in the inbox</span>
        </Link>
      ) : (
        row.leads
      );
    },
  };
  return [
    { ...dimension[groups[0] as Group], rowHeader: true },
    ...groups.slice(1).map((group) => dimension[group]),
    leads,
    count("site_visits", "Site visits"),
    count("booked", "Booked"),
  ];
}

function RangeForm({
  state,
  onApply,
}: {
  state: ReportState;
  onApply: (next: ReportState) => void;
}) {
  const [from, setFrom] = useState(state.from);
  const [to, setTo] = useState(state.to);
  const [group, setGroup] = useState<Group | "">(state.group);
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isCalendarDate(from) || !isCalendarDate(to)) {
      setError("Choose both dates.");
      return;
    }
    if (from > to) {
      setError(`The first date must be on or before ${formatCalendarDate(to)}.`);
      return;
    }
    setError(null);
    onApply({ from, to, group });
  }

  return (
    <form
      aria-label="Report dates"
      noValidate
      onSubmit={submit}
      className="flex flex-wrap items-end gap-3"
    >
      <TextField
        id="utm-from"
        label="From"
        type="date"
        value={from}
        error={error ?? undefined}
        onChange={(event) => setFrom(event.target.value)}
        className="flex-[0_1_190px]"
      />
      <TextField
        id="utm-to"
        label="To"
        type="date"
        value={to}
        onChange={(event) => setTo(event.target.value)}
        className="flex-[0_1_190px]"
      />
      <Select
        id="utm-group"
        label="Group by"
        value={group}
        options={[
          { value: "", label: "Source, medium, campaign and project" },
          ...(Object.keys(GROUPS) as Group[]).map((key) => ({
            value: key,
            label: `${GROUPS[key]} only`,
          })),
        ]}
        onChange={(event) => setGroup(event.target.value as Group | "")}
        className="flex-[1_1_340px] sm:max-w-md"
      />
      <Button type="submit" variant="secondary" className="mb-0.75">
        Show report
      </Button>
    </form>
  );
}
