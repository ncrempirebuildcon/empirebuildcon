"use client";
/**
 * /admin/redirects (`seo.manage`, ARCHITECTURE §16): old addresses that send visitors on to a new
 * one (301 or 308). Made by hand here, or automatically when a live page, post or project
 * changes its web address. Search, the origin filter and the page live in the address
 * (`?q=&origin=&page=&redirect=<id>|new`). The list is paged (25 a page; review L10): automatic
 * redirects pile up as pages and projects are renamed.
 *
 * The API refuses loops (A → B → A) and never stores a chain: adding A → B while B → C exists
 * stores A → C, and the reply's `notices` say so; both messages are shown as they come.
 * Hits and the last hit are counted by the website from Phase 5, so they stay empty for now.
 * SECURITY: the API refuses redirects from /admin, /api and other internal paths, and to hosts
 * other than our own domains; the form only explains early.
 */
import { useCallback, useMemo, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Alert, Button, Chip, Select, Table, TextField, type TableColumn } from "@empire/ui";
import { api, call, type Schema } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { keyOf, optionsOf } from "@/lib/labels";
import { problemMessage } from "@/lib/problems";
import { REDIRECTS_PATH } from "@/lib/routes";
import { ContentHeader } from "@/components/admin/content/ContentNav";
import { Pager, pageFrom } from "@/components/admin/Pager";
import { EmptyState, ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { useLoad } from "@/components/admin/useLoad";
import { useDirtyParts, useUnsavedChanges } from "@/components/admin/useUnsavedChanges";
import { ORIGIN, RedirectEditor } from "./RedirectEditor";

type Redirect = Schema<"Redirect">;
type Origin = Redirect["origin"];

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const PER_PAGE = 25;

interface Filters {
  q: string;
  origin: Origin | "";
  page: number;
  redirect: string | null;
}

function hrefFor(filters: Filters): string {
  const search = new URLSearchParams();
  if (filters.q) search.set("q", filters.q);
  if (filters.origin) search.set("origin", filters.origin);
  if (filters.page > 1) search.set("page", String(filters.page));
  if (filters.redirect) search.set("redirect", filters.redirect);
  const query = search.toString();
  return query ? `${REDIRECTS_PATH}?${query}` : REDIRECTS_PATH;
}

export function RedirectsScreen() {
  const params = useSearchParams();
  const router = useRouter();
  const raw = params.get("redirect") ?? "";
  const filters: Filters = {
    q: (params.get("q") ?? "").slice(0, 100),
    origin: keyOf(ORIGIN, params.get("origin") ?? "", ""),
    page: pageFrom(params.get("page")),
    redirect: raw === "new" || UUID_RE.test(raw) ? raw : null,
  };
  const [notices, setNotices] = useState<string[]>([]);
  // The redirect just saved: a new one sorts onto page 1, but stays open in the editor.
  const [lastSaved, setLastSaved] = useState<Redirect | null>(null);
  const parts = useDirtyParts();
  const { report } = parts;
  const onDirtyChange = useCallback((dirty: boolean) => report("redirect", dirty), [report]);
  const { dialog, leave } = useUnsavedChanges(parts.dirty);

  const list = useLoad(`redirects:${filters.q}:${filters.origin}:${filters.page}`, () =>
    call(
      api.GET("/api/v1/admin/redirects", {
        params: {
          query: {
            page: filters.page,
            per_page: PER_PAGE,
            q: filters.q || undefined,
            origin: filters.origin || undefined,
          },
        },
      }),
    ),
  );
  const items = useMemo(() => list.data?.items ?? [], [list.data]);
  const current =
    filters.redirect && filters.redirect !== "new"
      ? (items.find((r) => r.id === filters.redirect) ??
        (lastSaved?.id === filters.redirect ? lastSaved : undefined))
      : undefined;
  const go = (patch: Partial<Filters>) => {
    setNotices([]);
    leave(hrefFor({ ...filters, ...patch }), { replace: true });
  };

  const columns: TableColumn<Redirect>[] = [
    {
      key: "from",
      header: "From",
      rowHeader: true,
      cell: (r) => (
        <button
          type="button"
          onClick={() => go({ redirect: r.id })}
          className="min-h-11 text-left font-semibold [overflow-wrap:anywhere] text-ivory underline-offset-4 hover:underline"
        >
          {r.from_path}
        </button>
      ),
    },
    {
      key: "to",
      header: "To",
      cell: (r) => <span className="[overflow-wrap:anywhere]">{r.to_path}</span>,
    },
    { key: "code", header: "Code", cell: (r) => r.status_code },
    { key: "origin", header: "Made by", cell: (r) => ORIGIN[r.origin] },
    {
      key: "active",
      header: "Status",
      cell: (r) => (
        <Chip variant={r.is_active ? "published" : "draft"}>{r.is_active ? "On" : "Off"}</Chip>
      ),
    },
    { key: "hits", header: "Hits", className: "tabular-nums", cell: (r) => r.hits },
    {
      key: "last",
      header: "Last hit",
      className: "whitespace-nowrap",
      cell: (r) =>
        r.last_hit_at ? formatDateTime(r.last_hit_at) : <span className="text-muted">—</span>,
    },
  ];

  return (
    <>
      <ContentHeader
        current="redirects"
        description="Old web addresses that send visitors on to the right page. Hits are counted once the public site is live (Phase 5)."
        action={
          <Button onClick={() => go({ redirect: "new" })} disabled={filters.redirect === "new"}>
            + New redirect
          </Button>
        }
      />
      {notices.length > 0 ? (
        <Alert tone="success" title="Saved.">
          <ul className="flex list-disc flex-col gap-1 pl-5">
            {notices.map((notice) => (
              <li key={notice}>{notice}</li>
            ))}
          </ul>
        </Alert>
      ) : null}
      <SearchBar key={filters.q} filters={filters} onApply={go} />
      <div className="flex flex-wrap items-start gap-5">
        <section
          aria-label="Redirects table"
          className="flex min-w-0 flex-[2_1_520px] flex-col overflow-hidden rounded-card border border-line bg-noir-800"
        >
          {list.error ? (
            <ErrorPanel
              message={problemMessage(list.error, "Couldn't load redirects.")}
              onRetry={list.reload}
            />
          ) : !list.data ? (
            <LoadingPanel label="Loading redirects…" rows={4} />
          ) : (
            <>
              <Table
                caption="Redirects"
                captionHidden
                columns={columns}
                rows={items}
                rowKey={(r) => r.id}
                minWidth={760}
                busy={list.loading}
                rowClassName={(r) => (r.id === filters.redirect ? "bg-gold-tint" : undefined)}
                empty={
                  <EmptyState
                    title={
                      filters.q || filters.origin ? "No redirects match." : "No redirects yet."
                    }
                  />
                }
              />
              <div className="border-t border-line px-4 py-2">
                <Pager
                  page={list.data.meta.page}
                  perPage={list.data.meta.per_page}
                  total={list.data.meta.total}
                  pages={list.data.meta.pages}
                  hrefFor={(page) => hrefFor({ ...filters, page, redirect: null })}
                  noun="redirects"
                  singular="redirect"
                />
              </div>
            </>
          )}
        </section>
        {filters.redirect === "new" || current ? (
          <RedirectEditor
            key={filters.redirect ?? "none"}
            redirect={current ?? null}
            onDirtyChange={onDirtyChange}
            onSaved={async (saved, messages) => {
              await list.refresh().catch(() => undefined);
              setLastSaved(saved ?? null);
              setNotices(messages);
              // WHY not leave(): the editor's "saved" report reaches this screen a render later.
              router.replace(hrefFor({ ...filters, redirect: saved?.id ?? null }), {
                scroll: false,
              });
            }}
            onClose={() => go({ redirect: null })}
          />
        ) : filters.redirect && list.data ? (
          <Alert tone="info" title="This redirect isn't in the list.">
            It may be on another page of the list or outside the search, or it was deleted.
          </Alert>
        ) : null}
      </div>
      {dialog}
    </>
  );
}

function SearchBar({
  filters,
  onApply,
}: {
  filters: Filters;
  onApply: (patch: Partial<Filters>) => void;
}) {
  const [query, setQuery] = useState(filters.q);
  return (
    <form
      role="search"
      aria-label="Filter redirects"
      onSubmit={(event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        onApply({ q: query.trim(), page: 1, redirect: null });
      }}
      className="flex flex-wrap items-end gap-3"
    >
      <div className="flex min-w-60 flex-[2_1_240px] items-end gap-2">
        <TextField
          label="Search"
          type="search"
          placeholder="Either address"
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
        label="Made by"
        value={filters.origin}
        placeholder="Anyone"
        options={optionsOf(ORIGIN)}
        onChange={(event) =>
          onApply({ origin: keyOf(ORIGIN, event.target.value, ""), page: 1, redirect: null })
        }
        className="flex-[1_1_180px]"
      />
    </form>
  );
}
