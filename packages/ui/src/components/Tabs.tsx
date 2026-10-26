/**
 * Tabs: a tab list and its panels (WAI-ARIA Authoring Practices "Tabs", automatic activation),
 * styled like the CMS editor boards: gold text and a gold underline on the selected tab. With
 * `orientation="vertical"` the list is a column of sections with a gold bar on the selected one
 * (board NoirCmsSettings).
 *
 * Accessibility:
 * - Only the selected tab is in the Tab order; Arrow Left/Right (Up/Down when vertical), Home and
 *   End move between tabs and select them (DESIGN_SYSTEM §9: `aria-selected` on tabs).
 * - Each panel is labelled by its tab and focusable, so keyboard users land on the content.
 *
 * Use the same `idPrefix` on `Tabs` and every `TabPanel` so the ids line up.
 */
import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { cx } from "../cx";

export interface TabItem {
  /** Stable key, also used in the element ids (letters, digits and hyphens). */
  id: string;
  /** Visible tab text. */
  label: ReactNode;
}

export interface TabsProps {
  /** Accessible name of the tab list, e.g. "Project sections". */
  label: string;
  tabs: readonly TabItem[];
  /** The id of the selected tab. */
  selected: string;
  onSelect: (id: string) => void;
  /** Prefix for the tab and panel ids; must match the panels' `idPrefix`. */
  idPrefix: string;
  /** "vertical" for a column of sections (Arrow Up/Down); horizontal by default. */
  orientation?: "horizontal" | "vertical";
  className?: string;
}

export const tabId = (prefix: string, id: string) => `${prefix}-tab-${id}`;
export const panelId = (prefix: string, id: string) => `${prefix}-panel-${id}`;

export function Tabs({
  label,
  tabs,
  selected,
  onSelect,
  idPrefix,
  orientation = "horizontal",
  className,
}: TabsProps) {
  const refs = useRef(new Map<string, HTMLButtonElement>());
  const vertical = orientation === "vertical";
  const nextKey = vertical ? "ArrowDown" : "ArrowRight";
  const previousKey = vertical ? "ArrowUp" : "ArrowLeft";

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const last = tabs.length - 1;
    const target =
      event.key === nextKey
        ? index === last
          ? 0
          : index + 1
        : event.key === previousKey
          ? index === 0
            ? last
            : index - 1
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? last
              : null;
    if (target === null) return;
    event.preventDefault();
    const next = tabs[target];
    if (!next) return;
    onSelect(next.id);
    refs.current.get(next.id)?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label={label}
      aria-orientation={vertical ? "vertical" : undefined}
      className={cx(
        vertical
          ? "flex flex-col gap-0.5 rounded-card border border-line bg-noir-800 p-2"
          : "flex flex-wrap gap-1 border-b border-line",
        className,
      )}
    >
      {tabs.map((tab, index) => {
        const isSelected = tab.id === selected;
        return (
          <button
            key={tab.id}
            ref={(node) => {
              if (node) refs.current.set(tab.id, node);
              else refs.current.delete(tab.id);
            }}
            type="button"
            role="tab"
            id={tabId(idPrefix, tab.id)}
            aria-selected={isSelected}
            aria-controls={panelId(idPrefix, tab.id)}
            tabIndex={isSelected ? 0 : -1}
            onClick={() => onSelect(tab.id)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={cx(
              "min-h-11 px-3.5 text-small font-bold transition-colors duration-150",
              vertical && "rounded-tile py-2 text-left",
              isSelected
                ? vertical
                  ? "bg-gold-tint text-gold-300 shadow-[inset_3px_0_0_var(--color-gold-500)]"
                  : "text-gold-300 shadow-[inset_0_-2px_0_var(--color-gold-500)]"
                : "text-body hover:text-gold-300",
            )}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

export interface TabPanelProps {
  idPrefix: string;
  /** The tab this panel belongs to. */
  tabId: string;
  /** Whether this panel's tab is selected. Hidden panels stay mounted, so their state is kept. */
  selected: boolean;
  children: ReactNode;
  className?: string;
}

export function TabPanel({ idPrefix, tabId: id, selected, children, className }: TabPanelProps) {
  return (
    <div
      role="tabpanel"
      id={panelId(idPrefix, id)}
      aria-labelledby={tabId(idPrefix, id)}
      hidden={!selected}
      tabIndex={0}
      className={className}
    >
      {children}
    </div>
  );
}
