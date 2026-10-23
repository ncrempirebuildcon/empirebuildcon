"use client";
/**
 * The inbox's search and filters (board NoirCmsLeads): search by name, mobile digits or
 * reference; stage, project, owner, source and when the lead was received; and the quick filters
 * "New", "Unread", "Mine", "Unassigned" and "Spam" as toggle buttons (`aria-pressed`). Spam is
 * hidden from the inbox unless "Spam" is on, which shows only spam.
 *
 * Everything is written to the address by the caller (`onApply`), so a filtered inbox can be
 * shared, reloaded, or opened from a dashboard count.
 */
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Button, Select, TextField, cx, type SelectOption } from "@empire/ui";
import { addDays, istToday } from "@empire/ui/format";
import { formatCalendarDate } from "@/lib/dates";
import { GENERAL, type LeadFilters } from "@/lib/leads/filters";
import {
  LEAD_SOURCE,
  LEAD_STATUS,
  LEAD_STATUS_ORDER,
  type LeadSource,
  type LeadStatus,
} from "@/lib/leads/labels";

/** Received: a few presets, each a from/to pair in India dates; anything else is "custom". */
type Preset = "" | "today" | "7d" | "30d" | "custom";

function presetRange(preset: Preset, today: string): { from: string; to: string } {
  if (preset === "today") return { from: today, to: today };
  if (preset === "7d") return { from: addDays(today, -6), to: "" };
  if (preset === "30d") return { from: addDays(today, -29), to: "" };
  return { from: "", to: "" };
}

function presetOf(filters: LeadFilters, today: string): Preset {
  if (!filters.from && !filters.to) return "";
  for (const preset of ["today", "7d", "30d"] as const) {
    const range = presetRange(preset, today);
    if (range.from === filters.from && range.to === filters.to) return preset;
  }
  return "custom";
}

export interface LeadFilterBarProps {
  filters: LeadFilters;
  onApply: (next: Partial<LeadFilters>) => void;
  projects: SelectOption[];
  /** Staff to filter by owner; empty when the role sees only its own leads. */
  owners: SelectOption[];
  /** With `leads.read_all`: the Owner filter and the Mine / Unassigned quick filters. */
  canSeeAll: boolean;
  /** Hide the stage filter on the board, where every stage is a column. */
  showStage: boolean;
  /** Leads per stage under the other filters, shown in the Stage choices ("New · 12"). */
  stageCounts: Partial<Record<LeadStatus, number>> | null;
  clearHref: string | null;
}

export function LeadFilterBar({
  filters,
  onApply,
  projects,
  owners,
  canSeeAll,
  showStage,
  stageCounts,
  clearHref,
}: LeadFilterBarProps) {
  const [query, setQuery] = useState(filters.q);
  const today = istToday();
  const preset = presetOf(filters, today);
  const [custom, setCustom] = useState(preset === "custom");

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onApply({ q: query.trim() });
  }

  const quick: { label: string; pressed: boolean; toggle: () => void }[] = [
    {
      label: "New",
      pressed: filters.status === "new",
      toggle: () => onApply({ status: filters.status === "new" ? "" : "new" }),
    },
    {
      label: "Unread",
      pressed: filters.unread,
      toggle: () => onApply({ unread: !filters.unread }),
    },
  ];
  if (canSeeAll) {
    quick.push(
      {
        label: "Mine",
        pressed: filters.owner_id === "me",
        toggle: () => onApply({ owner_id: filters.owner_id === "me" ? "" : "me" }),
      },
      {
        label: "Unassigned",
        pressed: filters.owner_id === "unassigned",
        toggle: () => onApply({ owner_id: filters.owner_id === "unassigned" ? "" : "unassigned" }),
      },
    );
  }

  quick.push({
    label: "Spam",
    pressed: filters.spam,
    toggle: () => onApply({ spam: !filters.spam }),
  });

  const ownerOptions: SelectOption[] = [
    { value: "me", label: "Me" },
    { value: "unassigned", label: "Unassigned" },
    ...owners,
  ];

  return (
    <div className="flex flex-col gap-3">
      <form
        role="search"
        aria-label="Filter leads"
        onSubmit={onSubmit}
        className="flex flex-wrap items-end gap-3"
      >
        <div className="flex min-w-72 flex-[3_1_340px] items-end gap-2">
          <TextField
            id="leads-search"
            label="Search"
            type="search"
            name="q"
            placeholder="Name, mobile or reference"
            value={query}
            maxLength={100}
            onChange={(event) => setQuery(event.target.value)}
            className="flex-1"
          />
          <Button type="submit" variant="secondary" className="mb-0.75">
            Search
          </Button>
        </div>
        {showStage ? (
          <Select
            label="Stage"
            value={filters.status}
            placeholder="Any stage"
            options={LEAD_STATUS_ORDER.map((status) => ({
              value: status,
              label:
                stageCounts && stageCounts[status] !== undefined
                  ? `${LEAD_STATUS[status]} · ${stageCounts[status]}`
                  : LEAD_STATUS[status],
            }))}
            onChange={(event) => onApply({ status: event.target.value as LeadStatus | "" })}
            className="flex-[1_1_150px]"
          />
        ) : null}
        <Select
          label="Project"
          value={filters.project_id}
          placeholder="All projects"
          options={[{ value: GENERAL, label: "General enquiries (no project)" }, ...projects]}
          onChange={(event) => onApply({ project_id: event.target.value })}
          className="flex-[1_1_180px]"
        />
        {canSeeAll ? (
          <Select
            label="Owner"
            value={filters.owner_id}
            placeholder="Everyone"
            options={ownerOptions}
            onChange={(event) => onApply({ owner_id: event.target.value })}
            className="flex-[1_1_150px]"
          />
        ) : null}
        <Select
          label="Source"
          value={filters.source}
          placeholder="Any source"
          options={(Object.keys(LEAD_SOURCE) as LeadSource[]).map((source) => ({
            value: source,
            label: LEAD_SOURCE[source],
          }))}
          onChange={(event) => onApply({ source: event.target.value as LeadSource | "" })}
          className="flex-[1_1_160px]"
        />
        <Select
          label="Received"
          value={custom ? "custom" : preset}
          options={[
            { value: "", label: "Any time" },
            { value: "today", label: "Today" },
            { value: "7d", label: "Last 7 days" },
            { value: "30d", label: "Last 30 days" },
            { value: "custom", label: "Choose dates…" },
          ]}
          onChange={(event) => {
            const next = event.target.value as Preset;
            setCustom(next === "custom");
            if (next !== "custom") onApply(presetRange(next, today));
          }}
          className="flex-[1_1_150px]"
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

      {custom ? (
        <DateRange
          key={`${filters.from}|${filters.to}`}
          from={filters.from}
          to={filters.to}
          onApply={(range) => onApply(range)}
        />
      ) : null}

      <div role="group" aria-label="Quick filters" className="flex flex-wrap items-center gap-2">
        {quick.map((item) => (
          <button
            key={item.label}
            type="button"
            aria-pressed={item.pressed}
            onClick={item.toggle}
            className={cx(
              "min-h-11 rounded-pill border px-4 text-caption",
              item.pressed
                ? "border-gold-500 bg-gold-tint font-extrabold text-gold-300"
                : "border-line-strong bg-noir-800 font-semibold text-body hover:text-gold-300",
            )}
          >
            {item.label}
          </button>
        ))}
        {extraChips(filters).map((chip) => (
          <button
            key={chip.key}
            type="button"
            onClick={() => onApply(chip.clear)}
            className="min-h-11 rounded-pill border border-gold-500 bg-gold-tint px-4 text-caption font-bold text-gold-300"
          >
            {chip.label} <span aria-hidden="true">×</span>
            <span className="sr-only"> (remove this filter)</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * Filters that come in from links (dashboard counts, the UTM report) and have no control of their
 * own: each shows as a gold chip that removes it.
 */
function extraChips(
  filters: LeadFilters,
): { key: string; label: string; clear: Partial<LeadFilters> }[] {
  const chips: { key: string; label: string; clear: Partial<LeadFilters> }[] = [];
  if (filters.open) {
    chips.push({
      key: "open",
      label: filters.open === "true" ? "Still open (not booked or lost)" : "Booked or lost",
      clear: { open: "" },
    });
  }
  const tags = [
    ["utm_source", "Source tag"],
    ["utm_medium", "Medium"],
    ["utm_campaign", "Campaign"],
  ] as const;
  for (const [key, label] of tags) {
    if (filters[key]) chips.push({ key, label: `${label}: ${filters[key]}`, clear: { [key]: "" } });
  }
  return chips;
}

/** "Received from … to …" with an Apply button (dates in India time). */
function DateRange({
  from,
  to,
  onApply,
}: {
  from: string;
  to: string;
  onApply: (range: { from: string; to: string }) => void;
}) {
  const [start, setStart] = useState(from);
  const [end, setEnd] = useState(to);
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      aria-label="Received between"
      className="flex flex-wrap items-end gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (start && end && start > end) {
          setError(`The first date must be on or before ${formatCalendarDate(end)}.`);
          return;
        }
        setError(null);
        onApply({ from: start, to: end });
      }}
    >
      <TextField
        label="Received from"
        type="date"
        value={start}
        error={error ?? undefined}
        onChange={(event) => setStart(event.target.value)}
        className="flex-[0_1_200px]"
      />
      <TextField
        label="Received until"
        type="date"
        value={end}
        onChange={(event) => setEnd(event.target.value)}
        className="flex-[0_1_200px]"
      />
      <Button type="submit" variant="secondary" className="mb-0.75">
        Apply dates
      </Button>
    </form>
  );
}
