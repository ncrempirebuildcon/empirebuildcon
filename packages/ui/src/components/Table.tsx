/**
 * Table: a data table in the CMS style (design boards NoirCmsLeads and NoirCmsProject): gold,
 * letter-spaced column headers, hairline row rules, and horizontal scrolling on small screens.
 *
 * Accessibility (DESIGN_SYSTEM §9, "tables with headers"):
 * - Every table has a caption (visible or screen-reader only) and `scope`d column headers.
 * - A column marked `rowHeader` renders as `<th scope="row">`, so each row is announced by name.
 * - The scroll wrapper is a labelled, focusable region, so keyboard users can scroll it
 *   (axe rule "scrollable-region-focusable"). Wide tables scroll inside it, never the page.
 */
import { useId, type ReactNode } from "react";
import { cx } from "../cx";

export interface TableColumn<T> {
  /** Stable key for the column. */
  key: string;
  /** Header text. Shown in capitals by CSS, so screen readers still read normal words. */
  header: ReactNode;
  /** Keep the header for screen readers only (e.g. a column of action buttons). */
  headerHidden?: boolean;
  /** The cell for one row. */
  cell: (row: T, index: number) => ReactNode;
  /** Render this column's cells as row headers (`<th scope="row">`). Use for the name column. */
  rowHeader?: boolean;
  /** Extra classes for this column's cells, e.g. "tabular-nums" or "text-muted". */
  className?: string;
  /** Extra classes for this column's header, e.g. "w-0" for a column that hugs its buttons. */
  headerClassName?: string;
}

export interface TableProps<T> {
  /** What the table lists, e.g. "Projects". Required for screen readers. */
  caption: ReactNode;
  /** Show the caption only to screen readers (when a visible heading already names the table). */
  captionHidden?: boolean;
  columns: readonly TableColumn<T>[];
  rows: readonly T[];
  rowKey: (row: T) => string;
  /** Shown in place of the rows when there are none. */
  empty?: ReactNode;
  /** Minimum table width before the wrapper scrolls, e.g. 820. */
  minWidth?: number;
  /** Marks the table busy while new rows load. */
  busy?: boolean;
  /** Extra classes for one row, e.g. bold text for an unread lead. Never the only signal. */
  rowClassName?: (row: T) => string | undefined;
  className?: string;
}

export function Table<T>({
  caption,
  captionHidden = false,
  columns,
  rows,
  rowKey,
  empty,
  minWidth,
  busy = false,
  rowClassName,
  className,
}: TableProps<T>) {
  const captionId = useId();
  return (
    <div
      role="region"
      aria-labelledby={captionId}
      // WHY: a scrollable region must be reachable by keyboard; tabIndex 0 makes it focusable.
      tabIndex={0}
      // WHY relative: screen-reader-only headers are absolutely positioned; without a positioned
      // wrapper they escape the scroll area and make the whole page scroll sideways on phones.
      className={cx("relative overflow-x-auto", className)}
    >
      <table
        aria-busy={busy || undefined}
        className="w-full border-collapse text-table"
        style={minWidth ? { minWidth } : undefined}
      >
        <caption
          id={captionId}
          className={
            captionHidden ? "sr-only" : "px-4.5 pt-4 pb-2 text-left text-base font-bold text-ivory"
          }
        >
          {caption}
        </caption>
        <thead>
          <tr className="text-left text-xs tracking-[0.08em] text-gold-400 uppercase">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={cx(
                  "px-3 py-2.5 font-bold first:pl-4.5 last:pr-4.5",
                  column.headerClassName,
                )}
              >
                {column.headerHidden ? (
                  <span className="sr-only">{column.header}</span>
                ) : (
                  column.header
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && empty ? (
            <tr className="border-t border-line">
              <td colSpan={columns.length} className="px-4.5 py-4 text-center">
                {empty}
              </td>
            </tr>
          ) : (
            rows.map((row, index) => (
              <tr
                key={rowKey(row)}
                className={cx("border-t border-line align-middle", rowClassName?.(row))}
              >
                {columns.map((column) => {
                  const classes = cx(
                    "px-3 py-2.5 text-left first:pl-4.5 last:pr-4.5",
                    column.rowHeader && "font-bold text-ivory",
                    column.className,
                  );
                  return column.rowHeader ? (
                    <th key={column.key} scope="row" className={classes}>
                      {column.cell(row, index)}
                    </th>
                  ) : (
                    <td key={column.key} className={classes}>
                      {column.cell(row, index)}
                    </td>
                  );
                })}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
