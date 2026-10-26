/**
 * CodeList: a numbered list of short secret codes shown once, e.g. two-factor recovery codes
 * (board NoirCmsLogin's enrolment step). Large monospace text in a two-column grid.
 *
 * Accessibility (WCAG 2.1 AA): screen readers would read "k7fq-2mzp" as a word or skip the dash,
 * so each code is also spelled out for them ("k 7 f q, 2 m z p") and the visible text is hidden
 * from them. The spelled copy can't be selected (`select-none`), so copying the codes by hand
 * gets exactly what is on screen.
 *
 * SECURITY: the caller decides when the list is shown (only straight after the codes are made)
 * and must not keep the codes after the person confirms they saved them.
 */
import { cx } from "../cx";

export interface CodeListProps {
  /** The codes, in the order given by the server. */
  codes: readonly string[];
  /** Accessible name of the list, e.g. "Recovery codes". */
  label: string;
  className?: string;
}

/** "k7fq-2mzp" → "k 7 f q, 2 m z p": one character at a time, groups separated by a pause. */
export function spellCode(code: string): string {
  return code
    .split(/[-\s]+/)
    .filter(Boolean)
    .map((group) => [...group].join(" "))
    .join(", ");
}

export function CodeList({ codes, label, className }: CodeListProps) {
  return (
    <ol
      aria-label={label}
      className={cx(
        "grid grid-cols-1 gap-2 rounded-tile border border-line bg-noir-900 p-3 min-[360px]:grid-cols-2",
        className,
      )}
    >
      {codes.map((code, index) => (
        <li key={`${index}-${code}`} className="flex items-baseline gap-2">
          <span aria-hidden="true" className="w-5 text-right text-caption text-muted tabular-nums">
            {index + 1}.
          </span>
          <code aria-hidden="true" className="font-mono text-base tracking-wider text-ivory">
            {code}
          </code>
          <span className="sr-only select-none">{spellCode(code)}</span>
        </li>
      ))}
    </ol>
  );
}
