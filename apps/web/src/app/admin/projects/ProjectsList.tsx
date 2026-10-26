"use client";
/**
 * Projects list (board NoirCmsLeads for the filter bar, table and pager; NoirCmsProject for the
 * status chips). Search and filters live in the URL
 * (`?q=&status=&publish_state=&sales_status=&city=&blocked=true&page=`), so a filtered list can be
 * shared and the dashboard can link to it (ARCHITECTURE.md §8 "filters in the URL"). `blocked`
 * comes from the dashboard's "Drafts blocked from publishing" count and shows as a removable chip.
 *
 * "New project" needs `projects.write`; the API checks it again (SECURITY: hiding is not the guard).
 */
import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Alert,
  Button,
  Chip,
  Select,
  Table,
  TextField,
  buttonClasses,
  type TableColumn,
} from "@empire/ui";
import { api, call, type Schema } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import {
  PROJECT_STATUS,
  PROJECT_STATUS_CHIP,
  PUBLISH_STATE,
  PUBLISH_STATE_CHIP,
  SALES_STATUS,
  SALES_STATUS_CHIP,
  keyOf,
  optionsOf,
  type ProjectStatus,
  type PublishState,
  type SalesStatus,
} from "@/lib/labels";
import { problemMessage } from "@/lib/problems";
import { PROJECTS_PATH, projectPath } from "@/lib/routes";
import { EmptyState, ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { Pager } from "@/components/admin/Pager";
import { useLoad } from "@/components/admin/useLoad";
import { useAdminSession } from "../session-context";

type ProjectRow = Schema<"ProjectAdminSummary">;

const PER_PAGE = 20;

interface Filters {
  q: string;
  status: ProjectStatus | "";
  publish_state: PublishState | "";
  sales_status: SalesStatus | "";
  city: string;
  /** "true": can't be published yet (any publish blocker); "false": ready; "": all. */
  blocked: "" | "true" | "false";
  page: number;
}

/** Messages a redirect can leave for this page, e.g. after deleting a project. */
const NOTICES: Record<string, string> = {
  deleted: "The project was deleted.",
};

function readFilters(params: URLSearchParams): Filters {
  const pick = <K extends string>(labels: Record<K, string>, name: string): K | "" => {
    const value = params.get(name) ?? "";
    return keyOf(labels, value, "");
  };
  const page = Number.parseInt(params.get("page") ?? "1", 10);
  return {
    q: (params.get("q") ?? "").slice(0, 100),
    status: pick(PROJECT_STATUS, "status"),
    publish_state: pick(PUBLISH_STATE, "publish_state"),
    sales_status: pick(SALES_STATUS, "sales_status"),
    city: params.get("city") ?? "",
    blocked:
      params.get("blocked") === "true" ? "true" : params.get("blocked") === "false" ? "false" : "",
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

/** The list address for some filters; empty values and page 1 are left out. */
function listHref(filters: Filters): string {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(filters)) {
    if (value === "" || (name === "page" && value === 1)) continue;
    search.set(name, String(value));
  }
  const query = search.toString();
  return query ? `${PROJECTS_PATH}?${query}` : PROJECTS_PATH;
}

export function ProjectsList() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { can } = useAdminSession();
  const filters = useMemo(() => readFilters(params), [params]);
  // A one-off message from a redirect (e.g. after Delete): kept in state, removed from the address
  // so a reload or a shared link doesn't repeat it.
  const [notice] = useState(() => NOTICES[params.get("notice") ?? ""]);
  useEffect(() => {
    const url = new URL(window.location.href);
    if (!url.searchParams.has("notice")) return;
    url.searchParams.delete("notice");
    window.history.replaceState(null, "", url);
  }, []);
  const hasFilters = Boolean(
    filters.q ||
    filters.status ||
    filters.publish_state ||
    filters.sales_status ||
    filters.city ||
    filters.blocked,
  );

  const list = useLoad(listHref(filters), () =>
    call(
      api.GET("/api/v1/admin/projects", {
        params: {
          query: {
            page: filters.page,
            per_page: PER_PAGE,
            q: filters.q || undefined,
            status: filters.status || undefined,
            publish_state: filters.publish_state || undefined,
            sales_status: filters.sales_status || undefined,
            city: filters.city || undefined,
            blocked: filters.blocked ? filters.blocked === "true" : undefined,
          },
        },
      }),
    ),
  );
  const cities = useLoad("cities", () =>
    call(api.GET("/api/v1/admin/cities", { params: { query: { per_page: 100 } } })),
  );

  function apply(next: Partial<Filters>) {
    router.replace(listHref({ ...filters, page: 1, ...next }), { scroll: false });
  }

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-[60ch] text-small text-muted">
          Every project in the CMS, with its construction, sales and publishing status. Sample
          projects never show on the live site.
        </p>
        {can("projects.write") ? (
          <Link href={`${PROJECTS_PATH}/new`} className={buttonClasses("primary")}>
            + New project
          </Link>
        ) : null}
      </div>

      {notice ? <Alert tone="success">{notice}</Alert> : null}

      <FilterBar
        key={pathname + filters.q}
        filters={filters}
        cities={cities.data?.items ?? []}
        onApply={apply}
        clearHref={hasFilters ? PROJECTS_PATH : null}
      />

      {list.error ? (
        <ErrorPanel
          message={problemMessage(list.error, "Couldn't load projects.")}
          onRetry={list.reload}
        />
      ) : !list.data ? (
        <LoadingPanel label="Loading projects…" rows={5} />
      ) : (
        <>
          <section
            aria-label="Projects table"
            aria-busy={list.loading || undefined}
            className="overflow-hidden rounded-card border border-line bg-noir-800"
          >
            <Table
              caption="Projects"
              captionHidden
              columns={COLUMNS}
              rows={list.data.items}
              rowKey={(row) => row.id}
              minWidth={860}
              busy={list.loading}
              empty={
                hasFilters ? (
                  <EmptyState title="No projects match these filters.">
                    <Link href={PROJECTS_PATH} className="font-bold underline">
                      Clear filters
                    </Link>
                  </EmptyState>
                ) : (
                  <EmptyState title="No projects yet.">
                    <p className="text-small">
                      {can("projects.write")
                        ? "Add the first one with New project."
                        : "Projects appear here once an editor adds them."}
                    </p>
                  </EmptyState>
                )
              }
            />
          </section>
          <Pager
            page={list.data.meta.page}
            perPage={list.data.meta.per_page}
            total={list.data.meta.total}
            pages={list.data.meta.pages}
            hrefFor={(page) => listHref({ ...filters, page })}
            noun="projects"
            singular="project"
          />
        </>
      )}
    </>
  );
}

const COLUMNS: TableColumn<ProjectRow>[] = [
  {
    key: "name",
    header: "Name",
    rowHeader: true,
    cell: (row) => (
      <span className="flex flex-col gap-1">
        <span className="flex flex-wrap items-center gap-2">
          <Link
            href={projectPath(row.id)}
            className="text-ivory underline-offset-4 hover:underline"
          >
            {row.name}
          </Link>
          {row.is_sample ? <Chip variant="sample">SAMPLE</Chip> : null}
        </span>
        <span className="text-xs font-medium text-muted">/projects/{row.slug}</span>
      </span>
    ),
  },
  {
    key: "place",
    header: "City / locality",
    cell: (row) =>
      row.city ? (
        <span className="flex flex-col">
          <span>{row.city.name}</span>
          {row.locality ? <span className="text-xs text-muted">{row.locality.name}</span> : null}
        </span>
      ) : (
        <span className="text-muted">Not set</span>
      ),
  },
  {
    key: "status",
    header: "Construction",
    cell: (row) => (
      <Chip variant={PROJECT_STATUS_CHIP[row.status]}>{PROJECT_STATUS[row.status]}</Chip>
    ),
  },
  {
    key: "sales",
    header: "Sales",
    cell: (row) => (
      <Chip variant={SALES_STATUS_CHIP[row.sales_status]}>{SALES_STATUS[row.sales_status]}</Chip>
    ),
  },
  {
    key: "publish",
    header: "Publishing",
    cell: (row) =>
      row.publish_state ? (
        <Chip variant={PUBLISH_STATE_CHIP[row.publish_state]}>
          {PUBLISH_STATE[row.publish_state]}
        </Chip>
      ) : null,
  },
  {
    key: "updated",
    header: "Updated",
    className: "whitespace-nowrap text-muted",
    cell: (row) => (row.updated_at ? formatDateTime(row.updated_at) : "—"),
  },
];

function FilterBar({
  filters,
  cities,
  onApply,
  clearHref,
}: {
  filters: Filters;
  cities: Schema<"City">[];
  onApply: (next: Partial<Filters>) => void;
  clearHref: string | null;
}) {
  const [query, setQuery] = useState(filters.q);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onApply({ q: query.trim() });
  }

  return (
    <form
      role="search"
      aria-label="Filter projects"
      onSubmit={onSubmit}
      className="flex flex-wrap items-end gap-3"
    >
      <div className="flex min-w-60 flex-[2_1_240px] items-end gap-2">
        <TextField
          label="Search"
          type="search"
          name="q"
          placeholder="Name or web address"
          value={query}
          maxLength={100}
          onChange={(event) => setQuery(event.target.value)}
          className="flex-1"
        />
        <Button type="submit" variant="secondary" className="mb-0.75">
          Search
        </Button>
      </div>
      <Select
        label="Construction"
        value={filters.status}
        placeholder="Any"
        options={optionsOf(PROJECT_STATUS)}
        onChange={(event) => onApply({ status: keyOf(PROJECT_STATUS, event.target.value, "") })}
        className="flex-[1_1_160px]"
      />
      <Select
        label="Sales"
        value={filters.sales_status}
        placeholder="Any"
        options={optionsOf(SALES_STATUS)}
        onChange={(event) => onApply({ sales_status: keyOf(SALES_STATUS, event.target.value, "") })}
        className="flex-[1_1_140px]"
      />
      <Select
        label="Publishing"
        value={filters.publish_state}
        placeholder="Any"
        options={optionsOf(PUBLISH_STATE)}
        onChange={(event) =>
          onApply({ publish_state: keyOf(PUBLISH_STATE, event.target.value, "") })
        }
        className="flex-[1_1_140px]"
      />
      <Select
        label="City"
        value={filters.city}
        placeholder="Any city"
        options={cities.map((city) => ({ value: city.id, label: city.name }))}
        onChange={(event) => onApply({ city: event.target.value })}
        className="flex-[1_1_160px]"
      />
      {filters.blocked ? (
        <button
          type="button"
          onClick={() => onApply({ blocked: "" })}
          className="min-h-11 rounded-pill border border-gold-500 bg-gold-tint px-4 text-caption font-bold text-gold-300"
        >
          {filters.blocked === "true" ? "Blocked from publishing" : "Ready to publish"}{" "}
          <span aria-hidden="true">×</span>
          <span className="sr-only"> (remove this filter)</span>
        </button>
      ) : null}
      {clearHref ? (
        <Link
          href={clearHref}
          className="inline-flex min-h-11 items-center px-1 font-bold underline"
        >
          Clear filters
        </Link>
      ) : null}
    </form>
  );
}
