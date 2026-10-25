/**
 * Dates and times typed in India time for content schedules (page publish/unpublish, offer
 * start/end), turned into the UTC instants the API stores (CODE_STYLE §4: store UTC, show IST).
 *
 * A schedule is two inputs, a date and a time. Both empty means "no date"; half-filled is an
 * error, so a half-typed schedule is never sent.
 */
import { istDate, istTime, istToIso, isCalendarDate } from "@empire/ui/format";

export interface IstDateTime {
  /** "2026-10-24", or "" */
  date: string;
  /** "09:30" (24-hour), or "" */
  time: string;
}

export const NO_DATE: IstDateTime = { date: "", time: "" };

const TIME_RE = /^([01]\d|2[0-3]):([0-5]\d)$/;

/** The India date and time of a stored instant, for the inputs. */
export function fromInstant(iso: string | null | undefined): IstDateTime {
  if (!iso) return NO_DATE;
  return { date: istDate(iso), time: istTime(iso) };
}

/** True when both inputs are empty. */
export const isEmpty = (value: IstDateTime) => value.date === "" && value.time === "";

/**
 * The UTC instant for the inputs, null when both are empty, or a problem in words.
 * `defaultTime` fills an empty time (e.g. "00:00" for a start, "23:59" for an end) when given.
 */
export function toInstant(
  value: IstDateTime,
  defaultTime?: string,
): { instant: string | null; problem: ScheduleProblem | null } {
  if (isEmpty(value)) return { instant: null, problem: null };
  const time = value.time || defaultTime || "";
  if (!isCalendarDate(value.date)) {
    return { instant: null, problem: { field: "date", message: "Choose a date." } };
  }
  if (!TIME_RE.test(time)) {
    return { instant: null, problem: { field: "time", message: "Enter a time (IST)." } };
  }
  return { instant: istToIso(value.date, time), problem: null };
}

/** What is wrong with a schedule, and which of its two inputs shows it. */
export interface ScheduleProblem {
  field: "date" | "time";
  message: string;
}
