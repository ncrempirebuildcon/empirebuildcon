"use client";
/**
 * The "Some fields need attention" summary at the top of the page and post editors: the
 * message, then one button per problem that opens the tab (or block) where it is fixed, like the
 * project editor's summary. Problems also show next to their fields, so this is a way to get
 * there, not the only place they appear.
 */
import { Alert } from "@empire/ui";

export interface SaveProblem {
  key: string;
  /** "Web address: Use lower-case letters…" */
  text: string;
  /** Opens the tab or block that has the field. */
  onGo: () => void;
}

export function SaveErrorSummary({ title, problems }: { title: string; problems: SaveProblem[] }) {
  return (
    <Alert tone="error" title={title}>
      {problems.length > 0 ? (
        <ul className="mt-1 flex flex-col gap-1">
          {problems.map((problem) => (
            <li key={problem.key}>
              <button
                type="button"
                onClick={problem.onGo}
                className="min-h-11 text-left underline underline-offset-4"
              >
                {problem.text}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </Alert>
  );
}
