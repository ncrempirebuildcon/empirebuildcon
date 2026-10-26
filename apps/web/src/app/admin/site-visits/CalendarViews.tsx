"use client";
/**
 * The three ways the site-visit calendar shows a range of visits (board NoirCmsVisits):
 *
 * - Week: a real table, days as column headers and the time of day (morning, afternoon,
 *   evening) as row headers; each visit is a button that opens it in the side panel.
 * - Day: one day, its visits under the three times of day.
 * - List: a table of every visit in the range, the default on phones because it reads in order
 *   and needs no sideways scrolling.
 *
 * Every visit button says the lead, the project and the status in words, and carries
 * `aria-pressed` for the one open in the panel, so the calendar works with a keyboard and a
 * screen reader as well as with a mouse (DESIGN_SYSTEM §9).
 */
import { useId } from "react";
import { Chip, Table, cx, type TableColumn } from "@empire/ui";
import { addDays, istToday } from "@empire/ui/format";
import { formatDayLabel, formatTimeOfDay, weekdayShort } from "@/lib/dates";
import {
  VISIT_SLOT,
  VISIT_SLOTS,
  VISIT_STATUS,
  VISIT_STATUS_CHIP,
  slotLabel,
  type SiteVisit,
  type VisitSlot,
} from "@/lib/leads/labels";
import { isOpenVisit, visitDay, visitSlot } from "@/lib/leads/visits";

export interface CalendarViewProps {
  visits: SiteVisit[];
  selectedId: string | null;
  onSelect: (visit: SiteVisit) => void;
}

/** "Confirmed · 3:30 pm" / "To confirm" / "Done", the short status line on a visit button. */
function statusLine(visit: SiteVisit): string {
  if (visit.status === "confirmed" && visit.confirmed_for) {
    return `Confirmed · ${formatTimeOfDay(visit.confirmed_for)}`;
  }
  return visit.status === "requested" ? "To confirm" : VISIT_STATUS[visit.status];
}

function VisitButton({
  visit,
  selected,
  onSelect,
}: {
  visit: SiteVisit;
  selected: boolean;
  onSelect: (visit: SiteVisit) => void;
}) {
  const confirmed = visit.status === "confirmed";
  const closed = !isOpenVisit(visit);
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={() => onSelect(visit)}
      className={cx(
        "flex min-h-11 w-full flex-col gap-0.5 rounded-tag border px-2.5 py-2 text-left text-caption leading-snug",
        selected
          ? "border-gold-500 bg-gold-tint shadow-[0_0_0_2px_var(--color-gold-500)]"
          : confirmed
            ? "border-palm-line bg-palm-bg"
            : closed
              ? "border-line bg-noir-800"
              : "border-gold-line-strong bg-noir-700",
      )}
    >
      <strong className="text-small [overflow-wrap:anywhere] text-ivory">{visit.lead_name}</strong>
      <span className="[overflow-wrap:anywhere] text-body">{visit.project.name}</span>
      <span
        className={cx(
          "font-bold",
          confirmed ? "text-palm" : closed ? "text-muted" : "text-gold-300",
        )}
      >
        {statusLine(visit)}
      </span>
    </button>
  );
}

/** Visits grouped by day and time of day. */
function grid(visits: SiteVisit[]): Map<string, SiteVisit[]> {
  const cells = new Map<string, SiteVisit[]>();
  for (const visit of visits) {
    const day = visitDay(visit);
    if (!day) continue;
    const key = `${day}|${visitSlot(visit)}`;
    cells.set(key, [...(cells.get(key) ?? []), visit]);
  }
  for (const list of cells.values()) {
    list.sort((a, b) => (a.confirmed_for ?? "~").localeCompare(b.confirmed_for ?? "~"));
  }
  return cells;
}

export function WeekView({
  monday,
  visits,
  selectedId,
  onSelect,
  caption,
}: CalendarViewProps & { monday: string; caption: string }) {
  const days = Array.from({ length: 7 }, (_, index) => addDays(monday, index));
  const cells = grid(visits);
  const today = istToday();
  const captionId = useId();
  return (
    <div
      role="region"
      aria-labelledby={captionId}
      tabIndex={0}
      className="relative overflow-x-auto rounded-card border border-line bg-noir-800"
    >
      <table className="w-full min-w-[760px] table-fixed border-collapse text-small">
        <caption id={captionId} className="sr-only">
          {caption}
        </caption>
        <thead>
          <tr className="border-b border-line text-left">
            <th scope="col" className="w-24 px-3 py-3 text-xs font-normal text-muted">
              Time of day
            </th>
            {days.map((day) => (
              <th
                key={day}
                scope="col"
                className={cx(
                  "border-l border-line px-2.5 py-2.5 font-normal",
                  day === today && "bg-gold-tint",
                )}
              >
                <span className="block text-xs font-bold tracking-[0.08em] text-gold-400 uppercase">
                  {weekdayShort(day)}
                  {day === today ? <span className="sr-only"> (today)</span> : null}
                </span>
                <strong className="text-lg text-ivory tabular-nums">{Number(day.slice(8))}</strong>
                <span className="sr-only"> {formatDayLabel(day).slice(4)}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {VISIT_SLOTS.map((slot) => {
            const count = days.reduce(
              (n, day) => n + (cells.get(`${day}|${slot}`)?.length ?? 0),
              0,
            );
            return (
              <tr key={slot} className="border-b border-line align-top last:border-b-0">
                <th scope="row" className="px-3 py-3 text-left">
                  <span className="block text-small font-bold text-ivory">{VISIT_SLOT[slot]}</span>
                  <span className="text-xs font-normal text-muted">
                    {count} {count === 1 ? "visit" : "visits"}
                  </span>
                </th>
                {days.map((day) => {
                  const list = cells.get(`${day}|${slot}`) ?? [];
                  return (
                    <td
                      key={day}
                      className={cx(
                        "h-36 border-l border-line px-1.5 py-2",
                        list.length === 0 && "bg-noir-950/35",
                      )}
                    >
                      {list.length > 0 ? (
                        <ul className="flex flex-col gap-1.5">
                          {list.map((visit) => (
                            <li key={visit.id}>
                              <VisitButton
                                visit={visit}
                                selected={visit.id === selectedId}
                                onSelect={onSelect}
                              />
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <span className="sr-only">No visits</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function DayView({
  day,
  visits,
  selectedId,
  onSelect,
}: CalendarViewProps & { day: string }) {
  const cells = grid(visits);
  return (
    <div className="flex flex-col gap-3">
      {VISIT_SLOTS.map((slot: VisitSlot) => {
        const list = cells.get(`${day}|${slot}`) ?? [];
        return (
          <section
            key={slot}
            aria-labelledby={`day-${slot}`}
            className="flex flex-col gap-2 rounded-card border border-line bg-noir-800 p-3.5"
          >
            <h3 id={`day-${slot}`} className="text-small font-bold">
              {VISIT_SLOT[slot]}{" "}
              <span className="font-normal text-muted">
                · {list.length} {list.length === 1 ? "visit" : "visits"}
              </span>
            </h3>
            {list.length === 0 ? (
              <p className="text-caption text-muted">No visits.</p>
            ) : (
              <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {list.map((visit) => (
                  <li key={visit.id}>
                    <VisitButton
                      visit={visit}
                      selected={visit.id === selectedId}
                      onSelect={onSelect}
                    />
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}

export function ListView({
  visits,
  selectedId,
  onSelect,
  caption,
}: CalendarViewProps & { caption: string }) {
  const sorted = [...visits].sort((a, b) => {
    const day = (visitDay(a) ?? "").localeCompare(visitDay(b) ?? "");
    if (day !== 0) return day;
    return VISIT_SLOTS.indexOf(visitSlot(a)) - VISIT_SLOTS.indexOf(visitSlot(b));
  });
  const columns: TableColumn<SiteVisit>[] = [
    {
      key: "date",
      header: "Date",
      className: "whitespace-nowrap text-ivory tabular-nums",
      cell: (visit) => {
        const day = visitDay(visit);
        return day ? formatDayLabel(day) : "—";
      },
    },
    {
      key: "time",
      header: "Time",
      className: "whitespace-nowrap",
      cell: (visit) =>
        visit.confirmed_for
          ? formatTimeOfDay(visit.confirmed_for)
          : `${slotLabel(visit.preferred_slot)} (requested)`,
    },
    {
      key: "lead",
      header: "Lead",
      rowHeader: true,
      cell: (visit) => (
        <button
          type="button"
          aria-pressed={visit.id === selectedId}
          onClick={() => onSelect(visit)}
          className="min-h-11 text-left font-bold text-gold-300 underline-offset-4 hover:underline aria-pressed:underline"
        >
          {visit.lead_name ?? "Lead"}
        </button>
      ),
    },
    { key: "project", header: "Project", cell: (visit) => visit.project.name },
    {
      key: "status",
      header: "Status",
      cell: (visit) => (
        <Chip variant={VISIT_STATUS_CHIP[visit.status]} className="whitespace-nowrap">
          {VISIT_STATUS[visit.status]}
        </Chip>
      ),
    },
    {
      key: "handled",
      header: "Handled by",
      cell: (visit) => visit.handled_by?.name ?? <span className="text-muted">Not set</span>,
    },
  ];
  return (
    <>
      {/* WHY two layouts: a phone gets the visits as one readable column, grouped by day; wider
          screens get the board's table. Only one is ever displayed (and in the a11y tree). */}
      <PhoneList visits={sorted} selectedId={selectedId} onSelect={onSelect} caption={caption} />
      <div className="hidden overflow-hidden rounded-card border border-line bg-noir-800 sm:block">
        <Table
          caption={caption}
          columns={columns}
          rows={sorted}
          rowKey={(visit) => visit.id}
          rowClassName={(visit) => (visit.id === selectedId ? "bg-gold-tint/50" : undefined)}
          minWidth={720}
          empty={<p className="py-4 text-small">No site visits in these dates.</p>}
        />
      </div>
    </>
  );
}

function PhoneList({
  visits,
  selectedId,
  onSelect,
  caption,
}: CalendarViewProps & { caption: string }) {
  const days: { day: string; visits: SiteVisit[] }[] = [];
  for (const visit of visits) {
    const day = visitDay(visit) ?? "";
    const last = days.at(-1);
    if (last && last.day === day) last.visits.push(visit);
    else days.push({ day, visits: [visit] });
  }
  return (
    <section aria-label={caption} className="flex flex-col gap-3 sm:hidden">
      {days.length === 0 ? (
        <p className="rounded-card border border-line bg-noir-800 p-4 text-small">
          No site visits in these dates.
        </p>
      ) : (
        days.map(({ day, visits: list }) => (
          <div key={day} className="flex flex-col gap-2">
            <h3 className="text-small font-bold">{day ? formatDayLabel(day) : "No date"}</h3>
            <ul className="flex flex-col gap-2">
              {list.map((visit) => (
                <li key={visit.id} className="flex flex-col gap-1.5">
                  <VisitButton
                    visit={visit}
                    selected={visit.id === selectedId}
                    onSelect={onSelect}
                  />
                  <span className="px-1 text-caption text-muted">
                    {visit.confirmed_for
                      ? formatTimeOfDay(visit.confirmed_for)
                      : `${slotLabel(visit.preferred_slot)} (requested)`}
                    {" · "}
                    {visit.handled_by ? `Handled by ${visit.handled_by.name}` : "Not assigned"}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </section>
  );
}
