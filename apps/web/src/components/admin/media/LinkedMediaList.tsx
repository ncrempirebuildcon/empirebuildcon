"use client";
/**
 * The media attached to one owner and role, drawn as the board's photo grid, video cards or
 * document rows (NoirCmsProject, "Media manager"). Each item shows its order number, the cover
 * star (photos), a HIDDEN badge, its honest label, a "Show on website" switch, Move up/Move
 * down, "Edit details" and "Remove from …". State and saving live in `useMediaLinks`.
 *
 * Ordering: Move up/Move down on every item (keyboard and screen readers), and, for mouse users,
 * dragging an item onto another's place (`useDragReorder`). Both save through the same `move`.
 *
 * Accessibility:
 * - The list is an ordered list named by `label`; each item has a heading with its title, and
 *   every button names the item ("Move Tower A up", "Remove from project: Tower A").
 * - The cover star is a toggle button (`aria-pressed`, pinned or not); a hidden item's star is
 *   disabled with the reason ("Hidden items can't be the cover").
 * - A photo without an honest label stays hidden: its switch is disabled, described by the
 *   reason, with an "Add label" shortcut to the details dialog.
 * - Changes are announced in a polite live region; errors appear in an Alert (role="alert").
 *
 * SECURITY: buttons show only with `media.upload` (`canEdit`); the API checks it on every call.
 */
import { useState, type DragEvent, type ReactNode } from "react";
import {
  Alert,
  Button,
  Chip,
  ConfirmDialog,
  LiveRegion,
  ReorderButtons,
  Switch,
  cx,
} from "@empire/ui";
import { formatBytes } from "@/lib/media/files";
import { HONEST_LABEL_TONE, honestLabelText } from "@/lib/media/labels";
import type { LinkedMedia } from "@/lib/media/upload";
import { MediaDetailsDialog } from "./MediaDetailsDialog";
import { DocumentIcon, MediaThumb } from "./MediaThumb";
import { coverOf, moveButtonsId, useMediaLinks, type MediaLinks } from "./useMediaLinks";

export type MediaLayout = "photos" | "videos" | "documents";

export interface LinkedMediaListProps {
  items: readonly LinkedMedia[];
  layout: MediaLayout;
  /** Accessible name of the list, e.g. "Photos in display order". */
  label: string;
  /** Singular noun for messages, e.g. "photo". */
  noun: string;
  /** The owner in button text: "project", "update", "configuration". */
  ownerNoun: string;
  /** Show the cover star (the project's photos). */
  showCover?: boolean;
  /** False for single-item places (the brochure): no Move buttons and no dragging. */
  reorderable?: boolean;
  /** False without `media.upload`: the list is read-only. */
  canEdit: boolean;
  onChanged: () => Promise<unknown>;
  /** Element to focus after an item is removed. */
  focusAfterRemove: string;
  /** Prefix for element ids, unique on the page (e.g. "media-photos"). */
  idPrefix: string;
  /** Shown when there are no items. */
  emptyText: string;
  /** Extra content per item (e.g. the RERA QR's note). */
  extra?: (item: LinkedMedia) => ReactNode;
  className?: string;
}

export function LinkedMediaList(props: LinkedMediaListProps) {
  const links = useMediaLinks({
    items: props.items,
    onChanged: props.onChanged,
    noun: props.noun,
    focusAfterRemove: props.focusAfterRemove,
    scope: props.idPrefix,
  });
  const cover = props.showCover ? coverOf(links.ordered) : null;
  const ListTag = props.layout === "documents" ? DocumentRows : CardGrid;

  return (
    <div className={cx("flex flex-col gap-3", props.className)}>
      {links.error ? <Alert tone="error">{links.error}</Alert> : null}
      {links.ordered.length === 0 ? (
        <p className="rounded-tile border border-dashed border-line-strong px-4 py-3 text-small text-muted">
          {props.emptyText}
        </p>
      ) : (
        <ListTag {...props} links={links} coverId={cover} />
      )}
      <LiveRegion message={links.message} />
      <ConfirmDialog
        open={links.removing !== null}
        title={links.removing ? `Remove ${links.removing.title} from this ${props.ownerNoun}?` : ""}
        confirmLabel={`Remove from ${props.ownerNoun}`}
        tone="danger"
        busy={links.removeBusy}
        error={links.removeError}
        onCancel={links.cancelRemove}
        onConfirm={() => void links.confirmRemove()}
      >
        It stops showing on this {props.ownerNoun} straight away. The file stays in the media
        library, so it can be attached again.
      </ConfirmDialog>
      <MediaDetailsDialog
        media={links.editing}
        onClose={links.closeEdit}
        onSaved={links.detailsSaved}
      />
    </div>
  );
}

type ListProps = LinkedMediaListProps & { links: MediaLinks; coverId: string | null };

function CardGrid(props: ListProps) {
  const { links, layout } = props;
  const drag = useDragReorder(links, props.canEdit && props.reorderable !== false);
  return (
    <ol
      aria-label={props.label}
      className={cx(
        "grid gap-3.5",
        layout === "videos"
          ? "grid-cols-[repeat(auto-fill,minmax(min(100%,260px),1fr))]"
          : "grid-cols-[repeat(auto-fill,minmax(min(100%,190px),1fr))]",
      )}
    >
      {links.ordered.map((item, index) => (
        <li
          key={item.link_id}
          {...drag(item, index)}
          className={cx(
            "flex min-w-0 flex-col overflow-hidden rounded-tile border bg-noir-900",
            item.is_visible ? "border-line" : "border-dashed border-line-strong",
            "data-[drag-over]:outline-2 data-[drag-over]:outline-gold-400",
          )}
        >
          <div className="relative">
            <MediaThumb
              media={item}
              shape={layout === "videos" ? "video" : "photo"}
              dim={!item.is_visible}
            />
            <OrderBadge index={index} grip={props.canEdit && props.reorderable !== false} />
            {props.showCover ? (
              <CoverStar item={item} isCover={props.coverId === item.link_id} {...props} />
            ) : null}
            {layout === "videos" && item.duration_s ? (
              <span className="absolute right-2 bottom-2 rounded-tag bg-noir-900/85 px-2 py-0.5 text-xs font-bold text-ivory tabular-nums">
                {formatDuration(item.duration_s)}
              </span>
            ) : null}
            {!item.is_visible ? <HiddenBadge /> : null}
          </div>
          <div className="flex flex-1 flex-col gap-2 p-2.5">
            <ItemText item={item} />
            {props.extra?.(item)}
            <ItemControls item={item} index={index} {...props} />
          </div>
        </li>
      ))}
    </ol>
  );
}

function DocumentRows(props: ListProps) {
  const { links } = props;
  const reorderable = props.canEdit && props.reorderable !== false;
  const drag = useDragReorder(links, reorderable);
  return (
    <ol aria-label={props.label} className="flex flex-col gap-2.5">
      {links.ordered.map((item, index) => (
        <li
          key={item.link_id}
          {...drag(item, index)}
          className={cx(
            "flex flex-wrap items-center gap-3.5 rounded-tile border bg-noir-900 px-3.5 py-3",
            item.is_visible ? "border-line" : "border-dashed border-line-strong",
            "data-[drag-over]:outline-2 data-[drag-over]:outline-gold-400",
          )}
        >
          <span className="relative flex items-center gap-2.5">
            {reorderable ? (
              <>
                <DragGrip />
                <span className="w-6 text-center text-small font-extrabold text-ivory tabular-nums">
                  <span className="sr-only">Position </span>
                  {index + 1}
                </span>
              </>
            ) : null}
            <DocumentIcon />
          </span>
          <div className="flex min-w-0 flex-[1_1_220px] flex-col gap-0.5">
            <ItemText item={item} />
            {!item.is_visible ? (
              <span className="text-xs font-extrabold tracking-[0.08em] text-muted">HIDDEN</span>
            ) : null}
            {props.extra?.(item)}
          </div>
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-11 items-center text-caption font-bold underline underline-offset-4"
          >
            Open<span className="sr-only">{` ${item.title} (opens in a new tab)`}</span>
          </a>
          <ItemControls item={item} index={index} {...props} />
        </li>
      ))}
    </ol>
  );
}

/** The drag data type, so files dragged from the computer (type "Files") are never confused. */
const DRAG_TYPE = "application/x-empire-media-link";

/**
 * Drag-to-reorder for mouse users: drag an item and drop it on another item's place.
 * WHY only an extra: dragging needs a pointer and fine control, and screen readers can't follow
 * it (WCAG 2.1.1); the Move up/Move down buttons stay the way to reorder (ui Reorder.tsx).
 */
function useDragReorder(links: MediaLinks, enabled: boolean) {
  const [overId, setOverId] = useState<string | null>(null);
  const ours = (event: DragEvent) => Array.from(event.dataTransfer.types).includes(DRAG_TYPE);
  return (item: LinkedMedia, index: number) =>
    enabled
      ? {
          draggable: !links.moving,
          "data-drag-over": overId === item.link_id || undefined,
          onDragStart: (event: DragEvent) => {
            event.dataTransfer.setData(DRAG_TYPE, item.link_id);
            event.dataTransfer.effectAllowed = "move";
          },
          onDragOver: (event: DragEvent) => {
            if (!ours(event)) return;
            event.preventDefault();
            event.dataTransfer.dropEffect = "move";
            if (overId !== item.link_id) setOverId(item.link_id);
          },
          onDragLeave: () => setOverId((current) => (current === item.link_id ? null : current)),
          onDragEnd: () => setOverId(null),
          onDrop: (event: DragEvent) => {
            if (!ours(event)) return;
            event.preventDefault();
            setOverId(null);
            const from = links.ordered.findIndex(
              (other) => other.link_id === event.dataTransfer.getData(DRAG_TYPE),
            );
            if (from >= 0 && from !== index)
              void links.move(from, index, from > index ? "up" : "down");
          },
        }
      : {};
}

/** A grip on draggable items (decorative: the Move buttons are the accessible way). */
function DragGrip() {
  return (
    <svg
      aria-hidden="true"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      className="shrink-0 cursor-grab fill-body"
    >
      <circle cx="9" cy="6" r="1.8" />
      <circle cx="15" cy="6" r="1.8" />
      <circle cx="9" cy="12" r="1.8" />
      <circle cx="15" cy="12" r="1.8" />
      <circle cx="9" cy="18" r="1.8" />
      <circle cx="15" cy="18" r="1.8" />
    </svg>
  );
}

function OrderBadge({ index, grip }: { index: number; grip: boolean }) {
  return (
    <span className="absolute top-2 left-2 flex h-7.5 min-w-7.5 items-center justify-center gap-1 rounded-tag bg-noir-900/85 px-1.5 text-caption font-extrabold text-ivory tabular-nums">
      {grip ? <DragGrip /> : null}
      <span className="sr-only">Position </span>
      {index + 1}
    </span>
  );
}

function HiddenBadge() {
  return (
    <span className="absolute bottom-2 left-2 rounded-pill border border-line-strong bg-noir-900/90 px-2 py-0.5 text-[11px] font-extrabold text-muted">
      HIDDEN
    </span>
  );
}

function CoverStar({
  item,
  isCover,
  links,
  canEdit,
  idPrefix,
}: ListProps & { item: LinkedMedia; isCover: boolean }) {
  const blocked = !item.is_visible;
  const reasonId = `${idPrefix}-cover-reason-${item.link_id}`;
  const busy = links.isPending(item.link_id);
  return (
    <>
      <button
        type="button"
        aria-pressed={item.is_cover}
        aria-label={
          item.is_cover
            ? `Cover photo, pinned: ${item.title}`
            : `Make ${item.title} the cover photo`
        }
        aria-disabled={blocked || !canEdit || busy || undefined}
        aria-describedby={blocked ? reasonId : undefined}
        onClick={() => {
          if (blocked || !canEdit || busy) return;
          links.setPinned(item, !item.is_cover);
        }}
        className={cx(
          "absolute top-2 right-2 flex min-h-11 items-center gap-1 rounded-pill bg-noir-900/85 px-2.5 text-xs font-extrabold text-gold-300",
          (blocked || !canEdit) && "cursor-not-allowed",
        )}
      >
        <svg
          aria-hidden="true"
          width="15"
          height="15"
          viewBox="0 0 24 24"
          strokeWidth="1.6"
          className={cx("stroke-gold-400", isCover ? "fill-gold-400" : "fill-none")}
        >
          <path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z" />
        </svg>
        {isCover ? (item.is_cover ? "Cover · pinned" : "Cover") : null}
      </button>
      {blocked ? (
        <span id={reasonId} className="sr-only">
          Hidden items can&apos;t be the cover.
        </span>
      ) : null}
    </>
  );
}

function ItemText({ item }: { item: LinkedMedia }) {
  const label = honestLabelText(item.label, item.label_month);
  return (
    <>
      <h3 className="text-small font-bold text-ivory [overflow-wrap:anywhere]">{item.title}</h3>
      {item.is_sample ? (
        <Chip variant="sample" className="self-start">
          SAMPLE
        </Chip>
      ) : null}
      {item.kind === "image" ? (
        label && item.label ? (
          <span className={cx("text-caption font-bold", HONEST_LABEL_TONE[item.label])}>
            {label}
          </span>
        ) : (
          <span className="text-caption font-bold text-danger">
            {item.is_visible ? "No honest label yet" : "Hidden until labelled"}
          </span>
        )
      ) : null}
      <span className="text-xs text-muted">{metaLine(item)}</span>
    </>
  );
}

function ItemControls({
  item,
  index,
  links,
  canEdit,
  ownerNoun,
  idPrefix,
  reorderable = true,
}: ListProps & { item: LinkedMedia; index: number }) {
  const busy = links.isPending(item.link_id);
  // COMPLIANCE: a photo in a photo list can't be shown until it has an honest label (the API
  // refuses with 422), so its switch stays off with the reason and a shortcut to label it.
  const needsLabel = needsLabelToShow(item);
  const hintId = `${idPrefix}-label-hint-${item.link_id}`;
  return (
    <div className="mt-auto flex flex-col gap-1.5">
      <span className="flex flex-wrap items-center gap-x-2">
        <Switch
          checked={item.is_visible}
          onChange={(visible) => links.setVisible(item, visible)}
          label="Show on website"
          stateText={{ on: "Shown", off: "Hidden" }}
          context={item.title}
          busy={busy}
          disabled={!canEdit || needsLabel}
          aria-describedby={needsLabel ? hintId : undefined}
        />
        {busy ? <span className="text-caption font-semibold text-gold-300">Saving…</span> : null}
      </span>
      {needsLabel ? (
        <span className="flex flex-wrap items-center gap-x-2 text-caption text-muted">
          <span id={hintId}>Add an honest label to show it on the website.</span>
          {canEdit ? (
            <Button
              variant="tertiary"
              className="min-h-11"
              aria-label={`Add label: ${item.title}`}
              onClick={() => links.edit(item)}
            >
              Add label
            </Button>
          ) : null}
        </span>
      ) : null}
      {canEdit ? (
        <div className="flex flex-wrap items-center gap-1.5">
          {reorderable ? (
            <span id={moveButtonsId(idPrefix, item.link_id)} className="inline-flex">
              <ReorderButtons
                index={index}
                count={links.ordered.length}
                itemLabel={item.title}
                onMove={(from, to) => void links.move(from, to, to < from ? "up" : "down")}
                disabled={links.moving}
              />
            </span>
          ) : null}
          <Button
            variant="secondary"
            className="px-3.5"
            aria-label={`Edit details: ${item.title}`}
            onClick={() => links.edit(item)}
          >
            Edit details
          </Button>
          <Button
            variant="danger"
            className="px-3.5"
            aria-label={`Remove from ${ownerNoun}: ${item.title}`}
            onClick={() => links.askRemove(item)}
          >
            Remove from {ownerNoun}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/**
 * True when the item is a hidden photo in a photo list with no honest label yet (the API refuses
 * to show it). SAMPLE placeholders are exempt, as in the API.
 */
function needsLabelToShow(item: LinkedMedia): boolean {
  return (
    item.kind === "image" &&
    !item.label &&
    !item.is_sample &&
    !item.is_visible &&
    (item.role === "gallery" || item.role === "hero")
  );
}

/** "MP4 · 48.2 MB · 1920 × 1080" */
function metaLine(item: LinkedMedia): string {
  const parts = [item.format.toUpperCase(), formatBytes(item.bytes)];
  if (item.width && item.height) parts.push(`${item.width} × ${item.height}`);
  return parts.join(" · ");
}

/** 160.4 → "2:40" */
export function formatDuration(seconds: number): string {
  const total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}
