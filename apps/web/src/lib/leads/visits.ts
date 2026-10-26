/**
 * Where a site visit sits on the calendar (board NoirCmsVisits): its day and time of day in India,
 * and the one-line "when" the dashboard, lead detail and calendar show.
 *
 * D-016: a buyer asks for a date and a time of day (morning, afternoon, evening); sales agrees
 * the exact time by phone and records it (`confirmed_for`). Once confirmed, the agreed time wins:
 * the visit moves to that day and to the slot its time falls in.
 */
import { istDate, istTime } from "@empire/ui/format";
import { formatDayLabel, formatTimeOfDay } from "../dates";
import { slotLabel, type SiteVisit, type VisitSlot } from "./labels";

/** The visit's calendar day in India ("2026-10-24"), or null if it has neither date. */
export function visitDay(visit: SiteVisit): string | null {
  if (visit.confirmed_for) return istDate(visit.confirmed_for);
  return visit.preferred_date ?? null;
}

/**
 * The time of day the visit belongs to on the calendar.
 * WHY these bounds: the board's slots read as before noon, noon to 5 pm, and from 5 pm.
 */
export function visitSlot(visit: SiteVisit): VisitSlot {
  if (visit.confirmed_for) {
    const hour = Number(istTime(visit.confirmed_for).slice(0, 2));
    return hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening";
  }
  const slot = visit.preferred_slot;
  return slot === "afternoon" || slot === "evening" ? slot : "morning";
}

/** "Sat 24 Oct · 11:00 am" when confirmed, else "Sat 24 Oct · morning". */
export function visitWhen(visit: SiteVisit): string {
  const day = visitDay(visit);
  const time = visit.confirmed_for
    ? formatTimeOfDay(visit.confirmed_for)
    : slotLabel(visit.preferred_slot).toLowerCase();
  return day ? `${formatDayLabel(day)} · ${time}` : time;
}

/** True while staff can still act on the visit (confirm, reschedule, complete, no-show, cancel). */
export function isOpenVisit(visit: SiteVisit): boolean {
  return visit.status === "requested" || visit.status === "confirmed";
}
