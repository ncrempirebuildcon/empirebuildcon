/**
 * The small "SAT / 24" date tile from the dashboard, lead and visits boards. Decorative: the
 * day is always written out in the text next to it, so screen readers skip the tile.
 */
import { weekdayShort } from "@/lib/dates";

export function DayTile({ date }: { date: string }) {
  const day = Number(date.slice(8, 10));
  return (
    <span
      aria-hidden="true"
      className="flex w-13 shrink-0 flex-col rounded-tag border border-gold-line-strong bg-noir-700 py-1 text-center"
    >
      <span className="text-xs font-extrabold tracking-[0.08em] text-gold-400 uppercase">
        {weekdayShort(date)}
      </span>
      <strong className="text-xl leading-tight text-ivory tabular-nums">{day}</strong>
    </span>
  );
}
