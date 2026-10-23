/**
 * Date display for the CMS: "30 Sep 2026" and "30 Sep 2026, 9:41 pm", always in India time
 * (CODE_STYLE §4: store UTC, show Asia/Kolkata; DESIGN_SYSTEM §3 "Dates"), plus the day and week
 * labels of the site-visit calendar ("Sat 24 Oct", "26 Oct – 1 Nov 2026"). The calendar maths
 * (IST day of an instant, weeks from Monday) lives in `@empire/ui/format`, where it is tested.
 *
 * WHY our own month names: Intl's en-IN short month for September is "Sept" in newer ICU data,
 * while the design system writes "Sep". Only the numbers come from Intl, for the time zone.
 */
import { addDays, formatClock, istDate, istTime, weekdayIndex } from "@empire/ui/format";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const istParts = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Kolkata",
  year: "numeric",
  month: "numeric",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  hourCycle: "h23",
});

function parts(date: Date): Record<string, number> {
  const out: Record<string, number> = {};
  for (const part of istParts.formatToParts(date)) {
    if (part.type !== "literal") out[part.type] = Number(part.value);
  }
  return out;
}

/** "30 Sep 2026" for an ISO timestamp, in India time. */
export function formatDate(iso: string): string {
  const p = parts(new Date(iso));
  return `${p.day} ${MONTHS[(p.month ?? 1) - 1]} ${p.year}`;
}

/** "30 Sep 2026" for a calendar date ("2026-09-30"), with no time-zone shift. */
export function formatCalendarDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  return `${day} ${MONTHS[(month ?? 1) - 1]} ${year}`;
}

/** "30 Sep 2026, 9:41 pm" for an ISO timestamp, in India time. */
export function formatDateTime(iso: string): string {
  const p = parts(new Date(iso));
  const hour = p.hour ?? 0;
  const h12 = hour % 12 === 0 ? 12 : hour % 12;
  const minute = String(p.minute ?? 0).padStart(2, "0");
  return `${formatDate(iso)}, ${h12}:${minute} ${hour < 12 ? "am" : "pm"}`;
}

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** "Mon"…"Sun" for a calendar date ("2026-10-24" → "Sat"). */
export function weekdayShort(isoDate: string): string {
  return WEEKDAYS[weekdayIndex(isoDate)] ?? "";
}

/** "Sat 24 Oct" for a calendar date (the visits board's day label). */
export function formatDayLabel(isoDate: string): string {
  const [, month, day] = isoDate.split("-").map(Number);
  return `${weekdayShort(isoDate)} ${day} ${MONTHS[(month ?? 1) - 1]}`;
}

/** "26 Oct – 1 Nov 2026" for the seven days starting `monday` (the calendar's week heading). */
export function formatWeekRange(monday: string): string {
  const sunday = addDays(monday, 6);
  const [startYear, startMonth, startDay] = monday.split("-").map(Number);
  const [endYear, endMonth, endDay] = sunday.split("-").map(Number);
  const start =
    startYear === endYear
      ? `${startDay} ${MONTHS[(startMonth ?? 1) - 1]}`
      : formatCalendarDate(monday);
  return `${start} – ${endDay} ${MONTHS[(endMonth ?? 1) - 1]} ${endYear}`;
}

/** "11:00 am" for an ISO timestamp, in India time. */
export function formatTimeOfDay(iso: string): string {
  return formatClock(istTime(iso));
}

/** "Sat 24 Oct, 11:00 am" for an ISO timestamp, in India time (a confirmed visit). */
export function formatVisitTime(iso: string): string {
  return `${formatDayLabel(istDate(iso))}, ${formatTimeOfDay(iso)}`;
}
