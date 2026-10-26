"use client";
/**
 * Blog posts (board NoirCmsContent, "Blog posts"): title, category, author, status and date,
 * with search, category and status filters in the address (`?q=&category=&publish_state=&page=`).
 *
 * "+ New post" needs `content.write`; the API checks it again.
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
import { formatDate } from "@/lib/dates";
import { POST_CATEGORIES } from "@/lib/content/posts";
import {
  PUBLISH_STATE,
  PUBLISH_STATE_CHIP,
  keyOf,
  optionsOf,
  type PublishState,
} from "@/lib/labels";
import { problemMessage } from "@/lib/problems";
import { POSTS_PATH, postPath } from "@/lib/routes";
import { ContentHeader } from "@/components/admin/content/ContentNav";
import { EmptyState, ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { Pager } from "@/components/admin/Pager";
import { useLoad } from "@/components/admin/useLoad";
import { useAdminSession } from "../session-context";

type PostRow = Schema<"PostSummary">;

const PER_PAGE = 25;

interface Filters {
  q: string;
  category: string;
  publish_state: PublishState | "";
  page: number;
}

const NOTICES: Record<string, string> = { deleted: "The draft post was deleted." };

function readFilters(params: URLSearchParams): Filters {
  const page = Number.parseInt(params.get("page") ?? "1", 10);
  return {
    q: (params.get("q") ?? "").slice(0, 100),
    category: (params.get("category") ?? "").slice(0, 40),
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
  return query ? `${POSTS_PATH}?${query}` : POSTS_PATH;
}

export function PostsList() {
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
  const hasFilters = Boolean(filters.q || filters.category || filters.publish_state);

  const list = useLoad(listHref(filters), () =>
    call(
      api.GET("/api/v1/admin/posts", {
        params: {
          query: {
            page: filters.page,
            per_page: PER_PAGE,
            q: filters.q || undefined,
            category: filters.category || undefined,
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
      <ContentHeader
        current="posts"
        description="Blog and news posts. Posts about tax, stamp duty or the law: check every figure against the official source and link to it before publishing."
        action={
          can("content.write") ? (
            <Link href={`${POSTS_PATH}/new`} className={buttonClasses("primary")}>
              + New post
            </Link>
          ) : null
        }
      />
      {notice ? <Alert tone="success">{notice}</Alert> : null}
      <FilterBar
        key={pathname + filters.q}
        filters={filters}
        onApply={apply}
        clearHref={hasFilters ? POSTS_PATH : null}
      />
      {list.error ? (
        <ErrorPanel
          message={problemMessage(list.error, "Couldn't load posts.")}
          onRetry={list.reload}
        />
      ) : !list.data ? (
        <LoadingPanel label="Loading posts…" rows={5} />
      ) : (
        <>
          <section
            aria-label="Blog posts table"
            aria-busy={list.loading || undefined}
            className="overflow-hidden rounded-card border border-line bg-noir-800"
          >
            <Table
              caption="Blog posts"
              captionHidden
              columns={COLUMNS}
              rows={list.data.items}
              rowKey={(row) => row.id}
              minWidth={780}
              busy={list.loading}
              empty={
                hasFilters ? (
                  <EmptyState title="No posts match these filters.">
                    <Link href={POSTS_PATH} className="font-bold underline">
                      Clear filters
                    </Link>
                  </EmptyState>
                ) : (
                  <EmptyState title="No posts yet.">
                    <p className="text-small">
                      {can("content.write")
                        ? "Write the first one with + New post."
                        : "Posts appear here once an editor writes them."}
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
            noun="posts"
            singular="post"
          />
        </>
      )}
    </>
  );
}

const COLUMNS: TableColumn<PostRow>[] = [
  {
    key: "title",
    header: "Title",
    rowHeader: true,
    cell: (row) => (
      <span className="flex flex-col gap-1">
        <span className="flex flex-wrap items-center gap-2">
          <Link href={postPath(row.id)} className="text-ivory underline-offset-4 hover:underline">
            {row.title}
          </Link>
          {row.is_sample ? <Chip variant="sample">SAMPLE</Chip> : null}
        </span>
        <span className="text-xs font-medium text-muted">{row.path}</span>
      </span>
    ),
  },
  {
    key: "category",
    header: "Category",
    cell: (row) => row.category ?? <span className="text-muted">None</span>,
  },
  {
    key: "author",
    header: "Author",
    cell: (row) => row.author?.name ?? <span className="text-muted">—</span>,
  },
  {
    key: "state",
    header: "Status",
    cell: (row) => (
      <Chip variant={PUBLISH_STATE_CHIP[row.publish_state]}>
        {PUBLISH_STATE[row.publish_state]}
      </Chip>
    ),
  },
  {
    key: "date",
    header: "Publish date",
    className: "whitespace-nowrap",
    cell: (row) =>
      row.published_at ? formatDate(row.published_at) : <span className="text-muted">—</span>,
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
  const categories =
    POST_CATEGORIES.includes(filters.category) || !filters.category
      ? POST_CATEGORIES
      : [...POST_CATEGORIES, filters.category];
  return (
    <form
      role="search"
      aria-label="Filter posts"
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
        label="Category"
        value={filters.category}
        placeholder="All"
        options={categories.map((category) => ({ value: category, label: category }))}
        onChange={(event) => onApply({ category: event.target.value })}
        className="flex-[1_1_180px]"
      />
      <Select
        label="Status"
        value={filters.publish_state}
        placeholder="Any"
        options={optionsOf(PUBLISH_STATE)}
        onChange={(event) =>
          onApply({ publish_state: keyOf(PUBLISH_STATE, event.target.value, "") })
        }
        className="flex-[1_1_140px]"
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
