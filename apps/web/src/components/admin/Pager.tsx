"use client";
/**
 * "Showing 21–40 of 45" with Previous and Next links (board NoirCmsLeads). Links, not buttons,
 * so a page of results can be opened in a new tab or shared (filters live in the URL).
 */
import Link from "next/link";
import { cx } from "@empire/ui";

export interface PagerProps {
  page: number;
  perPage: number;
  total: number;
  pages: number;
  /** The address of a page of results, keeping the current filters. */
  hrefFor: (page: number) => string;
  /** What is listed, plural, e.g. "projects". */
  noun: string;
  /** The same word for exactly one, e.g. "project". */
  singular: string;
}

const linkClasses =
  "inline-flex min-h-11 items-center rounded-tile border px-4 text-caption font-bold";

export function Pager({ page, perPage, total, pages, hrefFor, noun, singular }: PagerProps) {
  const first = total === 0 ? 0 : (page - 1) * perPage + 1;
  const last = Math.min(page * perPage, total);
  return (
    <nav
      aria-label={`Pages of ${noun}`}
      className="flex flex-wrap items-center justify-between gap-3 text-caption text-muted"
    >
      <p role="status">
        {total === 0
          ? `No ${noun}`
          : `Showing ${first}–${last} of ${total} ${total === 1 ? singular : noun}`}
      </p>
      <span className="flex gap-2">
        {page > 1 ? (
          <Link
            href={hrefFor(page - 1)}
            className={cx(linkClasses, "border-line-strong bg-noir-800 text-ivory")}
          >
            Previous
          </Link>
        ) : (
          <span className={cx(linkClasses, "border-line text-muted")}>Previous</span>
        )}
        {page < pages ? (
          <Link
            href={hrefFor(page + 1)}
            className={cx(linkClasses, "border-line-strong bg-noir-800 text-ivory")}
          >
            Next
          </Link>
        ) : (
          <span className={cx(linkClasses, "border-line text-muted")}>Next</span>
        )}
      </span>
    </nav>
  );
}
