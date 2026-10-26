"use client";
/**
 * The lead inbox (/admin/leads, board NoirCmsLeads): newest first, paged, as a table or a
 * pipeline board. Search, filters, the view and the page live in the address
 * (`?q=&status=&project_id=&owner_id=&source=&utm_campaign=&from=&to=&read=false&is_spam=true`
 * `&view=board&page=`), the same names the API uses, so a dashboard count opens exactly its list.
 *
 * - "+ Add lead" (with `leads.update`) opens the manual-lead form; `?add=1` opens it directly
 *   (the dashboard's "+ Add lead").
 * - "Export CSV" only with `leads.export`, after a warning that the file holds personal data and
 *   the export is logged.
 *
 * SECURITY: a sales user without `leads.read_all` gets only their own leads from the API
 * (SECURITY.md §1); the Owner filter and the Mine / Unassigned quick filters are hidden for them
 * because they would change nothing. Hiding is never the protection.
 */
import Link from "next/link";
import { useEffect, useMemo, useOptimistic, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Button, SegmentedControl } from "@empire/ui";
import { api, call, type Schema } from "@/lib/api";
import {
  EMPTY_FILTERS,
  hasLeadFilters,
  leadsHref,
  leadsQuery,
  readLeadFilters,
  type InboxView,
  type LeadFilters,
} from "@/lib/leads/filters";
import { problemMessage } from "@/lib/problems";
import { EmptyState, ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { Pager } from "@/components/admin/Pager";
import { useLoad } from "@/components/admin/useLoad";
import { useProjectOptions, useStaffOptions } from "@/components/admin/leads/useLeadOptions";
import { useAdminSession } from "../session-context";
import { AddLeadDialog } from "./AddLeadDialog";
import { ExportLeads } from "./ExportLeads";
import { LeadFilterBar } from "./LeadFilterBar";
import { LeadsBoard } from "./LeadsBoard";
import { LeadsTable } from "./LeadsTable";

const PER_PAGE = 25;

export function LeadsInbox() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { can } = useAdminSession();
  const filters = useMemo(() => readLeadFilters(params), [params]);
  const canSeeAll = can("leads.read_all");
  const projects = useProjectOptions();
  const owners = useStaffOptions(canSeeAll);
  const [adding, setAdding] = useState(() => params.get("add") === "1" && can("leads.update"));
  const [addKey, setAddKey] = useState(0);

  // "?add=1" is a one-off instruction: drop it from the address so a reload doesn't reopen.
  useEffect(() => {
    const url = new URL(window.location.href);
    if (!url.searchParams.has("add")) return;
    url.searchParams.delete("add");
    window.history.replaceState(null, "", url);
  }, []);

  // WHY optimistic: the filters live in the address; `shown` shows the choice straight away
  // while the new address loads (React 19 useOptimistic), as on the media library.
  const [, startTransition] = useTransition();
  const [shown, setShown] = useOptimistic(
    filters,
    (_current: LeadFilters, next: LeadFilters) => next,
  );
  function apply(next: Partial<LeadFilters>) {
    const target = { ...filters, page: 1, ...next };
    startTransition(() => {
      setShown(target);
      router.replace(leadsHref(target), { scroll: false });
    });
  }

  // The table's page of leads. Loaded here so its per-stage counts can label the Stage filter.
  const tableView = filters.view === "table";
  const list = useLoad(tableView ? leadsHref(filters) : "board-view", () =>
    tableView
      ? call(
          api.GET("/api/v1/admin/leads", {
            params: { query: leadsQuery(filters, filters.page, PER_PAGE) },
          }),
        )
      : Promise.resolve(null),
  );

  const filtered = hasLeadFilters(filters);
  const clearHref = filtered ? leadsHref({ ...EMPTY_FILTERS, view: filters.view }) : null;

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-[60ch] text-small text-muted">
          {canSeeAll
            ? "Every enquiry, newest first. Open a lead to call, add notes and move it along."
            : "Leads assigned to you, newest first. Open a lead to call, add notes and move it along."}
        </p>
        <div className="flex flex-wrap items-center gap-2.5">
          <SegmentedControl<InboxView>
            label="View"
            value={shown.view}
            options={[
              { value: "table", label: "Table" },
              { value: "board", label: "Board" },
            ]}
            onChange={(view) => apply({ view, page: filters.page })}
          />
          {can("leads.export") ? <ExportLeads filters={filters} filtered={filtered} /> : null}
          {can("leads.update") ? (
            <Button
              onClick={() => {
                setAddKey((key) => key + 1);
                setAdding(true);
              }}
            >
              + Add lead
            </Button>
          ) : null}
        </div>
      </div>
      {can("leads.export") ? (
        <p id="export-note" className="-mt-2 text-caption text-muted sm:self-end">
          Export is for admin and super-admin only · every export is written to the audit log
        </p>
      ) : null}

      <LeadFilterBar
        key={pathname + filters.q}
        filters={shown}
        onApply={apply}
        projects={projects}
        owners={owners}
        canSeeAll={canSeeAll}
        showStage={shown.view === "table"}
        stageCounts={list.data?.status_counts ?? null}
        clearHref={clearHref}
      />

      {filters.view === "board" ? (
        <LeadsBoard filters={filters} canMove={can("leads.update")} />
      ) : (
        <LeadsList list={list} filters={filters} filtered={filtered} seesAll={canSeeAll} />
      )}

      {can("leads.update") ? (
        <AddLeadDialog
          key={addKey}
          open={adding}
          onClose={() => setAdding(false)}
          projects={projects}
          owners={can("leads.assign") ? owners : []}
        />
      ) : null}
    </>
  );
}

type LeadPage = Schema<"LeadList">;

function LeadsList({
  list,
  filters,
  filtered,
  seesAll,
}: {
  list: { data?: LeadPage | null; error?: unknown; loading: boolean; reload: () => void };
  filters: LeadFilters;
  filtered: boolean;
  /** With `leads.read_all`; otherwise the empty state talks about the user's own leads. */
  seesAll: boolean;
}) {
  if (list.error) {
    return (
      <ErrorPanel
        message={problemMessage(list.error, "Couldn't load leads.")}
        onRetry={list.reload}
      />
    );
  }
  if (!list.data) return <LoadingPanel label="Loading leads…" rows={6} />;

  return (
    <>
      <LeadsTable
        leads={list.data.items}
        busy={list.loading}
        empty={
          filtered ? (
            <EmptyState title="No leads match these filters.">
              <Link href={leadsHref({ ...EMPTY_FILTERS })} className="font-bold underline">
                Clear filters
              </Link>
            </EmptyState>
          ) : (
            <EmptyState title="No leads yet.">
              <p className="text-small">
                {seesAll
                  ? "Enquiries from the website appear here as soon as they arrive."
                  : "Leads given to you appear here as soon as they are assigned."}{" "}
                Calls and walk-ins can be added with Add lead.
              </p>
            </EmptyState>
          )
        }
      />
      <Pager
        page={list.data.meta.page}
        perPage={list.data.meta.per_page}
        total={list.data.meta.total}
        pages={list.data.meta.pages}
        hrefFor={(page) => leadsHref({ ...filters, page })}
        noun="leads"
        singular="lead"
      />
    </>
  );
}
