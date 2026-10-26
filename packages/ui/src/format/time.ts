/**
 * India-time calendar helpers for the CMS (leads, site visits, dashboard): which calendar day an
 * instant falls on in India, the week it belongs to, the IST wall-clock time of an instant, and
 * the UTC instant for a date and time a salesperson typed in India. Plus the "age" of a lead.
 *
 * Times are stored in UTC and shown in Asia/Kolkata (CODE_STYLE §4). Calendar dates are plain
 * "YYYY-MM-DD" strings, so a day never shifts when it passes through a browser in another zone.
 *
 * WHY a fixed +05:30 offset instead of Intl time zones: India has used one offset all year since
 * 1945 (no daylight saving), so the arithmetic is exact, and it behaves the same in every
 * browser, in Node and in jsdom regardless of the machine's own time zone.
 */

/** India Standard Time is UTC+05:30, all year. */
export const IST_OFFSET_MINUTES = 330;
const OFFSET_MS = IST_OFFSET_MINUTES * 60_000;
const DAY_MS = 86_400_000;
const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
const TIME_RE = /^([01]\d|2[0-3]):([0-5]\d)$/;

function toDate(instant: string | Date): Date {
  const date = typeof instant === "string" ? new Date(instant) : instant;
  if (Number.isNaN(date.getTime())) throw new RangeError(`Not a valid instant: ${String(instant)}`);
  return date;
}

/** Midnight UTC of a calendar date, for day arithmetic. Throws on a malformed date. */
function utcMidnight(date: string): number {
  const match = DATE_RE.exec(date);
  if (!match) throw new RangeError(`Not a calendar date (YYYY-MM-DD): ${date}`);
  const ms = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  // WHY: Date.UTC rolls 2026-02-31 over to March; a typed date that doesn't exist is an error.
  if (new Date(ms).toISOString().slice(0, 10) !== date) {
    throw new RangeError(`No such calendar date: ${date}`);
  }
  return ms;
}

/** The calendar date ("2026-10-24") an instant falls on in India. */
export function istDate(instant: string | Date): string {
  return new Date(toDate(instant).getTime() + OFFSET_MS).toISOString().slice(0, 10);
}

/** The IST wall-clock time ("09:05", 24-hour) of an instant, as `<input type="time">` wants it. */
export function istTime(instant: string | Date): string {
  return new Date(toDate(instant).getTime() + OFFSET_MS).toISOString().slice(11, 16);
}

/** Today's date in India. */
export function istToday(now: Date = new Date()): string {
  return istDate(now);
}

/**
 * The UTC instant (ISO 8601 with Z) for a date and a time typed in India.
 * Example: ("2026-10-24", "11:00") → "2026-10-24T05:30:00.000Z".
 *
 * @throws RangeError when the date or the time is malformed, so a half-typed field is never sent.
 */
export function istToIso(date: string, time: string): string {
  const match = TIME_RE.exec(time);
  if (!match) throw new RangeError(`Not a time (HH:MM): ${time}`);
  const minutes = Number(match[1]) * 60 + Number(match[2]);
  return new Date(utcMidnight(date) + minutes * 60_000 - OFFSET_MS).toISOString();
}

/** The calendar date `days` after (or before, when negative) `date`. */
export function addDays(date: string, days: number): string {
  return new Date(utcMidnight(date) + days * DAY_MS).toISOString().slice(0, 10);
}

/** Day of the week, Monday = 0 … Sunday = 6 (Indian calendars start the week on Monday). */
export function weekdayIndex(date: string): number {
  return (new Date(utcMidnight(date)).getUTCDay() + 6) % 7;
}

/** The Monday of the week that holds `date`. */
export function startOfWeek(date: string): string {
  return addDays(date, -weekdayIndex(date));
}

/** True when `date` is a real calendar date written "YYYY-MM-DD". */
export function isCalendarDate(date: string): boolean {
  try {
    utcMidnight(date);
    return true;
  } catch {
    return false;
  }
}

/** "11:00 am" / "6:30 pm" for a 24-hour "HH:MM" time. */
export function formatClock(time: string): string {
  const match = TIME_RE.exec(time);
  if (!match) throw new RangeError(`Not a time (HH:MM): ${time}`);
  const hour = Number(match[1]);
  const h12 = hour % 12 === 0 ? 12 : hour % 12;
  return `${h12}:${match[2]} ${hour < 12 ? "am" : "pm"}`;
}

/**
 * How long ago something happened, in the board's short form: "just now", "8 min", "3 h",
 * "2 d", "5 wk", then "3 mo" and "2 yr". A future instant (a clock a little ahead) is "just now".
 */
export function formatAge(instant: string | Date, now: Date = new Date()): string {
  const minutes = Math.floor((now.getTime() - toDate(instant).getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h`;
  const days = Math.floor(hours / 24);
  if (days < 14) return `${days} d`;
  if (days < 60) return `${Math.floor(days / 7)} wk`;
  if (days < 365) return `${Math.floor(days / 30)} mo`;
  return `${Math.floor(days / 365)} yr`;
}
