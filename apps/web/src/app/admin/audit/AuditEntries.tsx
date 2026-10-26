"use client";
/**
 * The audit log's table (board NoirCmsAudit): time and date in IST, who (name and role), the
 * kind of action as a chip with words, what it was about, the masked IP, and a Show/Hide button
 * that opens the entry's before/after lines in a row underneath.
 *
 * WHY a hand-made table and not `Table` from @empire/ui: each entry needs a second row spanning
 * every column for its details, which `Table` (one row per item) doesn't do.
 *
 * Accessibility: the details button says what it opens ("Show details of …"), carries
 * `aria-expanded` and `aria-controls`, and the before/after lists are named, with − and + signs
 * as well as colour (WCAG 1.4.1).
 */
import { useState } from "react";
import { Chip, type ChipVariant } from "@empire/ui";
import type { Schema } from "@/lib/api";
import { AUDIT_KINDS, actionWords, auditKind, auditLines, type AuditKind } from "@/lib/audit";
import { formatDate, formatTimeOfDay } from "@/lib/dates";
import { ROLE_LABELS } from "@/lib/labels";

type Entry = Schema<"AuditEntry">;

const KIND_CHIP: Record<AuditKind, ChipVariant> = {
  login: "upcoming",
  publish: "published",
  update: "ongoing",
  export: "scheduled",
  permission: "draft",
  erasure: "soldOut",
  other: "archived",
};

/** The entry's subject: the API's label when it sends one, else its type and a short id. */
export function entrySubject(entry: Entry): string {
  const label = (entry as Entry & { entity_label?: string | null }).entity_label;
  if (label) return label;
  const type = entry.entity_type.replaceAll("_", " ");
  const id = entry.entity_id.length > 12 ? `${entry.entity_id.slice(0, 8)}…` : entry.entity_id;
  return `${type.charAt(0).toUpperCase()}${type.slice(1)} ${id}`;
}

function actorRole(entry: Entry): string | null {
  const role = (entry.actor as (Entry["actor"] & { role?: string | null }) | null)?.role;
  return role ? (ROLE_LABELS[role] ?? role) : null;
}

export function AuditEntries({ entries }: { entries: readonly Entry[] }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    // WHY a focusable region: on a phone the table scrolls sideways inside it, not the page.
    // WHY relative: the screen-reader-only words are absolutely positioned; without a positioned
    // box here they would stretch the page sideways instead of scrolling with the table.
    <div
      role="region"
      aria-label="Audit entries table"
      tabIndex={0}
      className="relative overflow-x-auto"
    >
      <table className="w-full min-w-[900px] border-collapse text-table">
        <caption className="sr-only">Audit entries, newest first, times in India time</caption>
        <thead>
          <tr className="text-left text-xs tracking-[0.08em] text-gold-400 uppercase">
            <th scope="col" className="px-4.5 py-3">
              Time
            </th>
            <th scope="col" className="px-2.5 py-3">
              Person
            </th>
            <th scope="col" className="px-2.5 py-3">
              Action
            </th>
            <th scope="col" className="px-2.5 py-3">
              What
            </th>
            <th scope="col" className="px-2.5 py-3">
              IP
            </th>
            <th scope="col" className="px-4.5 py-3 text-right">
              Details
            </th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => {
            const kind = auditKind(entry.action);
            const isOpen = open === entry.id;
            const detailsId = `audit-entry-${entry.id}`;
            const words = actionWords(entry.action);
            const subject = entrySubject(entry);
            const role = actorRole(entry);
            return (
              <EntryRows
                key={entry.id}
                entry={entry}
                isOpen={isOpen}
                detailsId={detailsId}
                onToggle={() => setOpen(isOpen ? null : entry.id)}
                kindLabel={kind === "other" ? "Other" : AUDIT_KINDS[kind]}
                kindChip={KIND_CHIP[kind]}
                words={words}
                subject={subject}
                role={role}
              />
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function EntryRows({
  entry,
  isOpen,
  detailsId,
  onToggle,
  kindLabel,
  kindChip,
  words,
  subject,
  role,
}: {
  entry: Entry;
  isOpen: boolean;
  detailsId: string;
  onToggle: () => void;
  kindLabel: string;
  kindChip: ChipVariant;
  words: string;
  subject: string;
  role: string | null;
}) {
  const lines = auditLines(entry.changes);
  const hasDiff = lines.before.length > 0 || lines.after.length > 0;
  return (
    <>
      <tr className={`border-t border-line align-top ${isOpen ? "bg-gold-tint/50" : ""}`}>
        <td className="px-4.5 py-3 whitespace-nowrap tabular-nums">
          <span className="flex flex-col">
            <strong className="font-bold text-ivory">{formatTimeOfDay(entry.created_at)}</strong>
            <span className="text-xs text-muted">{formatDate(entry.created_at)}</span>
          </span>
        </td>
        <td className="px-2.5 py-3">
          <span className="flex flex-col">
            <span className="font-semibold text-ivory">{entry.actor?.name ?? "System"}</span>
            <span className="text-xs text-muted">{entry.actor ? (role ?? "") : "Automatic"}</span>
          </span>
        </td>
        <td className="px-2.5 py-3">
          <Chip variant={kindChip}>{kindLabel}</Chip>
        </td>
        <td className="px-2.5 py-3">
          <span className="flex flex-col">
            <span className="text-ivory">{words}</span>
            <span className="text-xs [overflow-wrap:anywhere] text-muted">{subject}</span>
          </span>
        </td>
        <td className="px-2.5 py-3 whitespace-nowrap">
          {entry.ip ? (
            <code className="text-caption">{entry.ip}</code>
          ) : (
            <span className="text-muted">—</span>
          )}
        </td>
        <td className="px-4.5 py-3 text-right">
          <button
            type="button"
            aria-expanded={isOpen}
            aria-controls={detailsId}
            onClick={onToggle}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-pill border border-line-strong bg-noir-700 px-3 text-caption font-bold whitespace-nowrap text-gold-300"
          >
            {isOpen ? "Hide" : "Show"}
            <span className="sr-only">
              {" "}
              details of {words}, {formatDate(entry.created_at)}
            </span>
            <span aria-hidden="true">{isOpen ? "▴" : "▾"}</span>
          </button>
        </td>
      </tr>
      {isOpen ? (
        <tr id={detailsId} className="bg-noir-900">
          <td colSpan={6} className="px-4.5 pt-1 pb-4.5">
            {hasDiff ? (
              <div className="grid gap-3 md:grid-cols-2">
                <ChangeList title="Before" sign="−" tone="text-danger" items={lines.before} />
                <ChangeList title="After" sign="+" tone="text-palm" items={lines.after} />
              </div>
            ) : null}
            <ul className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1.5 text-caption text-muted">
              {lines.info.map((line, index) => (
                <li key={`${index}-${line}`}>{line}</li>
              ))}
              <li>Action code: {entry.action}</li>
              <li>
                Record: {entry.entity_type} {entry.entity_id}
              </li>
              {!hasDiff && lines.info.length === 0 ? <li>No field changes recorded.</li> : null}
            </ul>
          </td>
        </tr>
      ) : null}
    </>
  );
}

function ChangeList({
  title,
  sign,
  tone,
  items,
}: {
  title: string;
  sign: string;
  tone: string;
  items: string[];
}) {
  return (
    <div className="overflow-hidden rounded-tile border border-line bg-noir-950">
      <p
        className={`border-b border-line px-3.5 py-2 text-xs font-extrabold tracking-[0.08em] uppercase ${tone}`}
      >
        {title}
      </p>
      <ul aria-label={title} className="flex flex-col gap-1 px-3.5 py-2.5">
        {items.length === 0 ? <li className="text-caption text-muted">(nothing)</li> : null}
        {items.map((item, index) => (
          <li key={`${index}-${item}`} className="flex gap-2.5 text-[13.5px]">
            <span aria-hidden="true" className={`font-extrabold ${tone}`}>
              {sign}
            </span>
            <code className={`whitespace-pre-wrap [overflow-wrap:anywhere] ${tone}`}>{item}</code>
          </li>
        ))}
      </ul>
    </div>
  );
}
