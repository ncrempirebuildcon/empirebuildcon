/**
 * Reordering without a mouse: "Move up" / "Move down" buttons for any ordered list or table,
 * plus a polite live region that says where the item went.
 *
 * WHY buttons and not only drag handles: dragging needs a pointer and fine motor control, and
 * screen readers cannot follow it (WCAG 2.1 SC 2.1.1 Keyboard). Drag handles may be added later
 * on top of these buttons, never instead of them.
 *
 * How it works:
 *   1. `moveItem` returns a new array with one item moved; callers save the new order.
 *   2. The buttons use `aria-disabled` at the ends of the list (not `disabled`), so focus stays on
 *      the button after the item reaches the top or bottom.
 *   3. `ReorderList` keys rows by id, so the focused button travels with its item, and announces
 *      "Tower B moved to position 1 of 3." through `LiveRegion`.
 */
import { useState, type ReactNode } from "react";
import { cx } from "../cx";

/** A copy of `items` with the item at `from` moved to index `to`. Out-of-range moves are no-ops. */
export function moveItem<T>(items: readonly T[], from: number, to: number): T[] {
  const copy = [...items];
  if (from < 0 || from >= copy.length || to < 0 || to >= copy.length || from === to) return copy;
  const [moved] = copy.splice(from, 1);
  copy.splice(to, 0, moved as T);
  return copy;
}

/** The sentence announced after a move. */
export function moveAnnouncement(label: string, to: number, count: number): string {
  return `${label} moved to position ${to + 1} of ${count}.`;
}

/** A visually hidden polite live region; screen readers read `message` whenever it changes. */
export function LiveRegion({ message }: { message: string }) {
  return (
    <p role="status" aria-live="polite" className="sr-only">
      {message}
    </p>
  );
}

export interface ReorderButtonsProps {
  /** Position of the item in the list (0-based). */
  index: number;
  /** Number of items in the list. */
  count: number;
  /** Name of the item for the button labels, e.g. "Tower A". */
  itemLabel: string;
  /** Called with the current and the new position. */
  onMove: (from: number, to: number) => void;
  /** Blocks both buttons, e.g. while a save is running. */
  disabled?: boolean;
  className?: string;
}

export function ReorderButtons({
  index,
  count,
  itemLabel,
  onMove,
  disabled = false,
  className,
}: ReorderButtonsProps) {
  return (
    <span className={cx("inline-flex gap-1", className)}>
      <MoveButton
        label={`Move ${itemLabel} up`}
        inactive={disabled || index === 0}
        onClick={() => onMove(index, index - 1)}
      >
        <Arrow direction="up" />
      </MoveButton>
      <MoveButton
        label={`Move ${itemLabel} down`}
        inactive={disabled || index >= count - 1}
        onClick={() => onMove(index, index + 1)}
      >
        <Arrow direction="down" />
      </MoveButton>
    </span>
  );
}

function MoveButton({
  label,
  inactive,
  onClick,
  children,
}: {
  label: string;
  inactive: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-disabled={inactive || undefined}
      // WHY: aria-disabled keeps the button focusable but does not block clicks by itself.
      onClick={() => {
        if (!inactive) onClick();
      }}
      className={cx(
        "inline-flex size-11 items-center justify-center rounded-pill border border-gold-500 text-gold-300",
        "transition-colors duration-150 hover:bg-gold-tint",
        inactive && "cursor-not-allowed opacity-45 hover:bg-transparent",
      )}
    >
      {children}
    </button>
  );
}

function Arrow({ direction }: { direction: "up" | "down" }) {
  return (
    <svg
      aria-hidden="true"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {direction === "up" ? <path d="M12 19V5M5 12l7-7 7 7" /> : <path d="M12 5v14M5 12l7 7 7-7" />}
    </svg>
  );
}

export interface ReorderListProps<T> {
  /** Accessible name of the list, e.g. "Towers in display order". */
  label: string;
  items: readonly T[];
  getKey: (item: T) => string;
  /** Short name of an item for button labels and announcements. */
  getLabel: (item: T) => string;
  /** Called with the reordered items after a move. */
  onReorder: (items: T[]) => void;
  /** The content of one row (everything except the move buttons). */
  renderItem: (item: T, index: number) => ReactNode;
  /** Hides the move buttons, e.g. for read-only users. */
  readOnly?: boolean;
  /** Blocks the move buttons, e.g. while a save is running. */
  disabled?: boolean;
  className?: string;
}

export function ReorderList<T>({
  label,
  items,
  getKey,
  getLabel,
  onReorder,
  renderItem,
  readOnly = false,
  disabled = false,
  className,
}: ReorderListProps<T>) {
  const [message, setMessage] = useState("");

  function move(from: number, to: number) {
    const item = items[from];
    if (item === undefined) return;
    onReorder(moveItem(items, from, to));
    setMessage(moveAnnouncement(getLabel(item), to, items.length));
  }

  return (
    <>
      <ol aria-label={label} className={cx("flex flex-col gap-2", className)}>
        {items.map((item, index) => (
          <li
            key={getKey(item)}
            className="flex flex-wrap items-center gap-3 rounded-tile border border-line bg-noir-900 px-3.5 py-2.5"
          >
            <div className="min-w-0 flex-1">{renderItem(item, index)}</div>
            {readOnly ? null : (
              <ReorderButtons
                index={index}
                count={items.length}
                itemLabel={getLabel(item)}
                onMove={move}
                disabled={disabled}
              />
            )}
          </li>
        ))}
      </ol>
      <LiveRegion message={message} />
    </>
  );
}
