"use client";
/**
 * "Leads by source" on the dashboard (board NoirCmsDashboard): the last 30 days of leads counted
 * by where they came from (project form, contact page, WhatsApp, …), as labelled bars, with a
 * link to the full UTM report. Counts only, no personal data; the API works them out with the
 * same object-level rule as the inbox and leaves spam out (`Dashboard.leads_by_source`).
 *
 * Each bar's number is written next to it, so the bars are decoration (`aria-hidden`) and the
 * list reads "Project form 16, WhatsApp 9…" for screen readers.
 */
import Link from "next/link";
import type { Schema } from "@/lib/api";
import { LEAD_SOURCE } from "@/lib/leads/labels";
import { UTM_REPORT_PATH } from "@/lib/routes";
import { Panel } from "@/components/admin/states";

type SourceCount = Schema<"SourceCount">;

export function LeadsBySource({
  rows,
  canOpenReport,
}: {
  rows: SourceCount[];
  /** With `leads.report`: the link to the full UTM report. */
  canOpenReport: boolean;
}) {
  const sorted = [...rows].filter((row) => row.count > 0).sort((a, b) => b.count - a.count);
  const total = sorted.reduce((sum, row) => sum + row.count, 0);
  const max = Math.max(1, ...sorted.map((row) => row.count));

  return (
    <Panel
      id="by-source"
      title="Leads by source"
      description={`Last 30 days · ${total} ${total === 1 ? "lead" : "leads"} · counts only, no personal data`}
    >
      {sorted.length === 0 ? (
        <p className="text-small">No leads in the last 30 days.</p>
      ) : (
        <ul className="flex flex-col gap-2.5">
          {sorted.map((row) => (
            <li
              key={row.source}
              className="grid grid-cols-[minmax(0,150px)_minmax(0,1fr)_40px] items-center gap-3 text-small"
            >
              <span className="truncate text-ivory">{LEAD_SOURCE[row.source]}</span>
              <span aria-hidden="true" className="h-3 overflow-hidden rounded-pill bg-line">
                <span
                  className="block h-full rounded-pill bg-linear-to-r from-gold-700 to-gold-400"
                  style={{ width: `${Math.round((row.count / max) * 100)}%` }}
                />
              </span>
              <strong className="text-right text-gold-300 tabular-nums">{row.count}</strong>
            </li>
          ))}
        </ul>
      )}
      {canOpenReport ? (
        <Link
          href={UTM_REPORT_PATH}
          className="inline-flex min-h-11 items-center text-small font-bold"
        >
          Full UTM report (by source, campaign and project)
        </Link>
      ) : null}
    </Panel>
  );
}
