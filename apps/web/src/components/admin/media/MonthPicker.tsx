"use client";
/**
 * "Month taken" for an honest label: a month and a year select side by side, shared by the
 * details dialog and the label question before a photo batch uploads.
 *
 * WHY two selects and not `<input type="month">`: Safari and Firefox show that as a plain text
 * box, where staff would have to guess the format.
 * The API refuses future months, so only this year and the 15 before it are offered, and
 * `monthProblem` says when the chosen month is still ahead (India time).
 */
import { Select } from "@empire/ui";
import { MONTH_NAMES } from "@/lib/media/labels";

/** This month in India time, as [year, month 1–12]. */
export function thisMonth(): [number, number] {
  const [year, month] = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" })
    .format(new Date())
    .split("-")
    .map(Number);
  return [year ?? 1970, month ?? 1];
}

function yearOptions(): { value: string; label: string }[] {
  const [now] = thisMonth();
  return Array.from({ length: 16 }, (_, index) => {
    const year = String(now - index);
    return { value: year, label: year };
  });
}

/**
 * What is wrong with a chosen month, or null.
 * @param required True for progress photos, which always need their month.
 */
export function monthProblem(month: string, year: string, required: boolean): string | null {
  if (!month && !year) return required ? "Choose the month the photo was taken." : null;
  if (!month || !year) return "Choose both the month and the year, or neither.";
  const [nowYear, nowMonth] = thisMonth();
  if (Number(year) * 12 + Number(month) > nowYear * 12 + nowMonth) {
    return "The month can't be in the future.";
  }
  return null;
}

export function MonthPicker({
  month,
  year,
  onChange,
  required,
  error,
}: {
  /** "1"–"12" or "". */
  month: string;
  /** "2026" or "". */
  year: string;
  onChange: (next: { month?: string; year?: string }) => void;
  required: boolean;
  error?: string;
}) {
  return (
    <fieldset className="grid grid-cols-2 gap-3">
      <legend className="mb-1.5 text-small font-semibold text-ivory">
        Month taken{" "}
        <span className="font-normal text-muted">{required ? "(required)" : "(optional)"}</span>
      </legend>
      <Select
        label="Month"
        value={month}
        placeholder="Month"
        options={MONTH_NAMES.map((name, index) => ({ value: String(index + 1), label: name }))}
        onChange={(e) => onChange({ month: e.target.value })}
        error={error}
      />
      <Select
        label="Year"
        value={year}
        placeholder="Year"
        options={yearOptions()}
        onChange={(e) => onChange({ year: e.target.value })}
      />
    </fieldset>
  );
}
