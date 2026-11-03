/**
 * Filters, paging and breadcrumbs for the catalogue lists (task 5.3).
 *
 * The filter form is a plain `<form method="get">`: it works without JavaScript, and the URL
 * is the state (ARCHITECTURE §14 "Filters live in the URL"), so a filtered list can be shared
 * or bookmarked. Paging links keep the filters (`filterHref`).
 */
import Link from "next/link";
import { JsonLd } from "@/components/JsonLd";
import { breadcrumbLd } from "@/lib/public/seo";
import type { components } from "@empire/api-client";
import {
  BHKS,
  BUDGETS,
  type CatalogueFilters,
  filterHref,
  pageWindow,
  PROPERTY_TYPES,
} from "@/lib/public/catalogue";

type City = components["schemas"]["PublicCity"];

const selectClass =
  "min-h-11 w-full rounded-input border border-field-line bg-noir-700 px-3 text-base text-ivory";
const labelClass = "text-caption font-semibold tracking-[0.08em] text-gold-400 uppercase";

export function FilterForm({
  action,
  filters,
  cities,
  sorts,
  showSearch = true,
  showCity = true,
  showStatus = true,
}: {
  action: string;
  filters: CatalogueFilters;
  cities: City[];
  sorts: readonly { value: string; label: string }[];
  showSearch?: boolean;
  showCity?: boolean;
  showStatus?: boolean;
}) {
  return (
    <form
      method="get"
      action={action}
      role="search"
      aria-label="Filter the list"
      className="grid grid-cols-1 gap-4 rounded-card border border-line bg-noir-800 p-4 sm:grid-cols-2 lg:grid-cols-4"
    >
      {showSearch ? (
        <label className="flex flex-col gap-1.5 sm:col-span-2 lg:col-span-4">
          <span className={labelClass}>Search</span>
          <input
            type="search"
            name="q"
            defaultValue={filters.q ?? ""}
            maxLength={200}
            placeholder="Project, locality or city"
            className={selectClass}
          />
        </label>
      ) : null}
      {showCity ? (
        <label className="flex flex-col gap-1.5">
          <span className={labelClass}>City</span>
          <select name="city" defaultValue={filters.city ?? ""} className={selectClass}>
            <option value="">All cities</option>
            {cities.map((c) => (
              <option key={c.slug} value={c.slug}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {showStatus ? (
        <label className="flex flex-col gap-1.5">
          <span className={labelClass}>Status</span>
          <select name="status" defaultValue={filters.status ?? ""} className={selectClass}>
            <option value="">Any status</option>
            <option value="ongoing">Under construction</option>
            <option value="completed">Ready to move</option>
            <option value="upcoming">Upcoming</option>
          </select>
        </label>
      ) : null}
      <label className="flex flex-col gap-1.5">
        <span className={labelClass}>Type</span>
        <select name="type" defaultValue={filters.type ?? ""} className={selectClass}>
          <option value="">All types</option>
          {PROPERTY_TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1.5">
        <span className={labelClass}>BHK</span>
        <select name="bhk" defaultValue={filters.bhk ?? ""} className={selectClass}>
          <option value="">Any</option>
          {BHKS.map((b) => (
            <option key={b.value} value={b.value}>
              {b.label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1.5">
        <span className={labelClass}>Budget</span>
        <select name="budget" defaultValue={filters.budget ?? ""} className={selectClass}>
          <option value="">Any budget</option>
          {BUDGETS.map((b) => (
            <option key={b.value} value={b.value}>
              {b.label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1.5">
        <span className={labelClass}>Sort</span>
        <select name="sort" defaultValue={filters.sort ?? ""} className={selectClass}>
          {sorts.map((s) => (
            <option key={s.value} value={s.value === "recommended" ? "" : s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </label>
      <div className="flex flex-wrap items-end gap-3 sm:col-span-2 lg:col-span-4">
        <button
          type="submit"
          className="min-h-11 rounded-pill bg-gold-500 px-6 font-extrabold text-noir-900 hover:bg-gold-400"
        >
          Show results
        </button>
        <Link href={action} className="inline-flex min-h-11 items-center px-2 font-semibold">
          Clear all
        </Link>
      </div>
    </form>
  );
}

export function Pager({
  path,
  filters,
  page,
  pages,
  noun,
}: {
  path: string;
  filters: CatalogueFilters;
  page: number;
  pages: number;
  noun: string;
}) {
  if (pages <= 1) return null;
  const link = "inline-flex min-h-11 min-w-11 items-center justify-center rounded-pill px-3";
  return (
    <nav
      aria-label={`Pages of ${noun}`}
      className="flex flex-wrap items-center justify-center gap-1"
    >
      {page > 1 ? (
        <Link href={filterHref(path, filters, { page: page - 1 })} className={link} rel="prev">
          ‹ Previous
        </Link>
      ) : null}
      {pageWindow(page, pages).map((p, i) =>
        p === null ? (
          <span key={`gap-${i}`} className="px-2 text-muted" aria-hidden="true">
            …
          </span>
        ) : p === page ? (
          <span
            key={p}
            aria-current="page"
            className={`${link} bg-gold-500 font-extrabold text-noir-900`}
          >
            <span className="sr-only">Page </span>
            {p}
          </span>
        ) : (
          <Link key={p} href={filterHref(path, filters, { page: p })} className={link}>
            <span className="sr-only">Page </span>
            {p}
          </Link>
        ),
      )}
      {page < pages ? (
        <Link href={filterHref(path, filters, { page: page + 1 })} className={link} rel="next">
          Next ›
        </Link>
      ) : null}
    </nav>
  );
}

/** Visible breadcrumbs, and the same trail as BreadcrumbList structured data (task 5.6). */
export function Breadcrumbs({
  items,
  structuredData = true,
}: {
  items: { href?: string; label: string }[];
  /** False on sample data, which is never offered to search engines (D-047). */
  structuredData?: boolean;
}) {
  return (
    <nav aria-label="Breadcrumb" className="text-small text-muted">
      {structuredData ? <JsonLd data={breadcrumbLd(items)} /> : null}
      <ol className="flex flex-wrap items-center gap-1.5">
        {items.map((item, i) => (
          <li key={`${item.label}-${i}`} className="flex items-center gap-1.5">
            {i > 0 ? <span aria-hidden="true">/</span> : null}
            {item.href ? (
              <Link href={item.href} className="inline-flex min-h-11 items-center">
                {item.label}
              </Link>
            ) : (
              <span aria-current="page" className="text-body">
                {item.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

/** "12 projects · available first, sold out last" in a polite status region. */
export function ResultCount({ total, noun }: { total: number; noun: [string, string] }) {
  return (
    <p role="status" className="text-small text-muted">
      {total} {total === 1 ? noun[0] : noun[1]} · available first, sold out last
    </p>
  );
}
