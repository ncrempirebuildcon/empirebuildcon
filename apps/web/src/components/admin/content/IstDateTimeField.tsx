"use client";
/**
 * A date and time typed in India time (e.g. "Publish on", "Ends"), as a labelled group of two
 * native inputs, with "Clear" when something is set. Converted to UTC by lib/content/schedule.ts.
 *
 * Accessibility: a fieldset with a visible legend; each input has its own label ("Date",
 * "Time (IST)"); a problem is shown under, and linked to, the input it concerns.
 */
import { Button, TextField } from "@empire/ui";
import type { IstDateTime, ScheduleProblem } from "@/lib/content/schedule";

export interface IstDateTimeFieldProps {
  /** Visible legend, e.g. "Publish on". */
  legend: string;
  value: IstDateTime;
  onChange: (value: IstDateTime) => void;
  /** Id prefix for the two inputs. */
  id: string;
  /** A problem from the form's checks or the API, shown under the date or the time. */
  error?: ScheduleProblem | null;
  hint?: string;
  disabled?: boolean;
  /** Earliest date allowed in the date picker ("YYYY-MM-DD"). */
  min?: string;
}

export function IstDateTimeField({
  legend,
  value,
  onChange,
  id,
  error,
  hint,
  disabled,
  min,
}: IstDateTimeFieldProps) {
  const set = value.date !== "" || value.time !== "";
  return (
    <fieldset
      disabled={disabled}
      aria-describedby={hint ? `${id}-hint` : undefined}
      className="flex min-w-0 flex-col gap-2"
    >
      <legend className="mb-1 text-small font-semibold text-ivory">{legend}</legend>
      <div className="flex flex-wrap items-end gap-3">
        <TextField
          id={`${id}-date`}
          label="Date"
          type="date"
          min={min}
          value={value.date}
          error={error?.field === "date" ? error.message : undefined}
          onChange={(event) => onChange({ ...value, date: event.target.value })}
          className="min-w-40 flex-[1_1_160px]"
        />
        <TextField
          id={`${id}-time`}
          label="Time (IST)"
          type="time"
          step={300}
          value={value.time}
          error={error?.field === "time" ? error.message : undefined}
          onChange={(event) => onChange({ ...value, time: event.target.value })}
          className="min-w-32 flex-[1_1_130px]"
        />
        {set && !disabled ? (
          <Button
            variant="tertiary"
            className="min-h-11"
            aria-label={`Clear ${legend}`}
            onClick={() => onChange({ date: "", time: "" })}
          >
            Clear
          </Button>
        ) : null}
      </div>
      {hint ? (
        <p id={`${id}-hint`} className="text-caption text-muted">
          {hint}
        </p>
      ) : null}
    </fieldset>
  );
}
