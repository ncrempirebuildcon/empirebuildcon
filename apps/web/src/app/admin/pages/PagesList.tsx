"use client";
/**
 * The pages list (/admin/pages): every page with its kind, publishing state, place in the menu
 * and schedule. Search and filters live in the address (`?q=&kind=&publish_state=&page=`), like
 * the projects list, so a filtered list can be shared or reloaded.
 *
 * "+ New page" needs `content.write`; the API checks it again (SECURITY: hiding is not the guard).
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
import { PAGE_KIND, type PageKind } from "@/lib/content/labels";
import {
  PUBLISH_STATE,
  PUBLISH_STATE_CHIP,
  keyOf,
  optionsOf,
  type PublishState,
} from "@/lib/labels";
import { problemMessage } from "@/lib/problems";
import { PAGES_PATH, pagePath } from "@/lib/routes";
import { EmptyState, ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { Pager } from "@/components/admin/Pager";
import { useLoad } from "@/components/admin/useLoad";
import { useAdminSession } from "../session-context";

type PageRow = Schema<"PageSummary">;

const PER_PAGE = 25;

interface Filters {
  q: string;
  kind: PageKind | "";
  publish_state: PublishState | "";
  page: number;
}

const NOTICES: Record<string, string> = {
  deleted: "The draft page was deleted.",
};

function readFilters(params: URLSearchParams): Filters {
  const page = Number.parseInt(params.get("page") ?? "1", 10);
  return {
    q: (params.get("q") ?? "").slice(0, 100),
    kind: keyOf(PAGE_KIND, params.get("kind") ?? "", ""),
    publish_state: keyOf(PUBLISH_STATE, params.get("publish_state") ?? "", ""),
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

function listHref(filters: Filters): string {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(filters)) {
    if (value === "" || (name === "page" && value === 1)) continue;
    search.set(name, String(value));
  }
  const query = search.toString();
  return query ? `${PAGES_PATH}?${query}` : PAGES_PATH;
}

export function PagesList() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { can } = useAdminSession();
  const filters = useMemo(() => readFilters(params), [params]);
  const [notice] = useState(() => NOTICES[params.get("notice") ?? ""]);
  useEffect(() => {
    const url = new URL(window.location.href);
    if (!url.searchParams.has("notice")) return;
    url.searchParams.delete("notice");
    window.history.replaceState(null, "", url);
  }, []);
  const hasFilters = Boolean(filters.q || filters.kind || filters.publish_state);

  const list = useLoad(listHref(filters), () =>
    call(
      api.GET("/api/v1/admin/pages", {
        params: {
          query: {
            page: filters.page,
            per_page: PER_PAGE,
            q: filters.q || undefined,
            kind: filters.kind || undefined,
            publish_state: filters.publish_state || undefined,
          },
        },
      }),
    ),
  );

  function apply(next: Partial<Filters>) {
    router.replace(listHref({ ...filters, page: 1, ...next }), { scroll: false });
  }

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-[70ch] text-small text-muted">
          The website&apos;s pages, built from blocks. Pages that come with the website (the system
          pages and the privacy, terms and disclaimer pages) keep their address and can&apos;t be
          deleted; legal pages stay marked DRAFT until the owner approves their text.
        </p>
        {can("content.write") ? (
          <Link href={`${PAGES_PATH}/new`} className={buttonClasses("primary")}>
            + New page
          </Link>
        ) : null}
      </div>

      {notice ? <Alert tone="success">{notice}</Alert> : null}

      <FilterBar
        key={pathname + filters.q}
        filters={filters}
        onApply={apply}
        clearHref={hasFilters ? PAGES_PATH : null}
      />

      {list.error ? (
        <ErrorPanel
          message={problemMessage(list.error, "Couldn't load pages.")}
          onRetry={list.reload}
        />
      ) : !list.data ? (
        <LoadingPanel label="Loading pages…" rows={5} />
      ) : (
        <>
          <section
            aria-label="Pages table"
            aria-busy={list.loading || undefined}
            className="overflow-hidden rounded-card border border-line bg-noir-800"
          >
            <Table
              caption="Pages"
              captionHidden
              columns={COLUMNS}
              rows={list.data.items}
              rowKey={(row) => row.id}
              minWidth={860}
              busy={list.loading}
              empty={
                hasFilters ? (
                  <EmptyState title="No pages match these filters.">
                    <Link href={PAGES_PATH} className="font-bold underline">
                      Clear filters
                    </Link>
                  </EmptyState>
                ) : (
                  <EmptyState title="No pages yet.">
                    <p className="text-small">
                      The site&apos;s own pages appear here after the database seed runs.
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
            noun="pages"
            singular="page"
          />
        </>
      )}
    </>
  );
}

function scheduleText(row: PageRow): string {
  const parts: string[] = [];
  if (row.publish_at) parts.push(`Publishes ${formatDateTime(row.publish_at)}`);
  if (row.unpublish_at) parts.push(`Unpublishes ${formatDateTime(row.unpublish_at)}`);
  return parts.join(" · ");
}

const COLUMNS: TableColumn<PageRow>[] = [
  {
    key: "title",
    header: "Page",
    rowHeader: true,
    cell: (row) => (
      <span className="flex flex-col gap-1">
        <span className="flex flex-wrap items-center gap-2">
          <Link href={pagePath(row.id)} className="text-ivory underline-offset-4 hover:underline">
            {row.title}
          </Link>
          {row.is_sample ? <Chip variant="sample">SAMPLE</Chip> : null}
          {row.is_draft_text ? <Chip variant="sample">DRAFT TEXT</Chip> : null}
        </span>
        <span className="text-xs font-medium text-muted">{row.path}</span>
      </span>
    ),
  },
  { key: "kind", header: "Kind", cell: (row) => PAGE_KIND[row.kind] },
  {
    key: "state",
    header: "Publishing",
    cell: (row) => (
      <Chip variant={PUBLISH_STATE_CHIP[row.publish_state]}>
        {PUBLISH_STATE[row.publish_state]}
      </Chip>
    ),
  },
  {
    key: "nav",
    header: "In the menu",
    cell: (row) =>
      row.show_in_nav ? (
        <span>
          Yes{row.nav_order !== null && row.nav_order !== undefined ? ` · ${row.nav_order}` : ""}
        </span>
      ) : (
        <span className="text-muted">No</span>
      ),
  },
  {
    key: "schedule",
    header: "Schedule",
    cell: (row) => scheduleText(row) || <span className="text-muted">None</span>,
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
  onApply,
  clearHref,
}: {
  filters: Filters;
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
      aria-label="Filter pages"
      onSubmit={onSubmit}
      className="flex flex-wrap items-end gap-3"
    >
      <div className="flex min-w-60 flex-[2_1_240px] items-end gap-2">
        <TextField
          label="Search"
          type="search"
          name="q"
          placeholder="Title or web address"
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
        label="Kind"
        value={filters.kind}
        placeholder="Any kind"
        options={optionsOf(PAGE_KIND)}
        onChange={(event) => onApply({ kind: keyOf(PAGE_KIND, event.target.value, "") })}
        className="flex-[1_1_180px]"
      />
      <Select
        label="Publishing"
        value={filters.publish_state}
        placeholder="Any state"
        options={optionsOf(PUBLISH_STATE)}
        onChange={(event) =>
          onApply({ publish_state: keyOf(PUBLISH_STATE, event.target.value, "") })
        }
        className="flex-[1_1_160px]"
      />
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
