"use client";
/**
 * The Blocks tab of the page editor (board NoirCmsPage): the ordered block list on the left, a
 * preview of the selected block in the middle, and its settings on the right. Changes stay in
 * the editor until "Save draft" sends the whole ordered list (`PUT /pages/{id}/blocks`).
 *
 * How it works:
 *   1. Selecting a block (its name button, `aria-pressed`) shows its preview and settings.
 *   2. "+ Add block" opens the palette (each type with its description); the new block goes
 *      after the selected one, is selected, and focus moves to its settings heading.
 *   3. Move up/Move down reorder; "Show on website" hides a block without deleting it; Delete
 *      asks first. Every change is announced in a polite live region ("Text moved to position
 *      2 of 5."), and focus stays on the control that was used (rows are keyed by block).
 *   4. Blocks with problems (from the form checks or the API) say "Needs attention" in the list,
 *      in words, so colour is never the only signal.
 *
 * Accessibility (WCAG 2.1 AA): everything works with the keyboard; drag-and-drop is optional
 * and not offered, because the move buttons already do the job for everyone (spec §2).
 */
import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  ConfirmDialog,
  Dialog,
  ReorderButtons,
  SegmentedControl,
  Switch,
  cx,
  moveAnnouncement,
  moveItem,
} from "@empire/ui";
import { BLOCK_TYPES, BLOCK_TYPE_ORDER, type BlockType } from "@/lib/content/blockTypes";
import type { FieldErrors } from "@/lib/problems";
import { EmptyState } from "@/components/admin/states";
import { blockCaption, blockName, emptyBlock, type DraftBlock } from "./blockDraft";
import { BlockForm } from "./BlockForm";
import { BlockPreview } from "./BlockPreview";

export interface BlocksTabProps {
  blocks: readonly DraftBlock[];
  onChange: (blocks: DraftBlock[]) => void;
  selectedKey: string | null;
  onSelect: (key: string | null) => void;
  /** Problems per block key (form checks and API errors). */
  errors: ReadonlyMap<string, FieldErrors>;
  /** Without `content.write`: read-only. */
  canWrite: boolean;
  canUpload: boolean;
  onBusyChange: (busy: boolean) => void;
  /** Says something in the editor's live region. */
  announce: (message: string) => void;
}

const selectId = (key: string) => `block-select-${key}`;

export function BlocksTab({
  blocks,
  onChange,
  selectedKey,
  onSelect,
  errors,
  canWrite,
  canUpload,
  onBusyChange,
  announce,
}: BlocksTabProps) {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [deleting, setDeleting] = useState<DraftBlock | null>(null);
  const [previewSize, setPreviewSize] = useState<"desktop" | "mobile">("desktop");
  const settingsHeading = useRef<HTMLHeadingElement>(null);
  const [focusSettings, setFocusSettings] = useState(0);
  const selectedIndex = blocks.findIndex((block) => block.key === selectedKey);
  const selected = selectedIndex >= 0 ? blocks[selectedIndex] : undefined;
  const shown = blocks.filter((block) => block.is_visible).length;

  useEffect(() => {
    if (focusSettings > 0) settingsHeading.current?.focus();
  }, [focusSettings]);

  function update(next: DraftBlock) {
    onChange(blocks.map((block) => (block.key === next.key ? next : block)));
  }

  function move(from: number, to: number) {
    const block = blocks[from];
    if (!block) return;
    onChange(moveItem(blocks, from, to));
    announce(moveAnnouncement(blockName(block), to, blocks.length));
    // WHY: when React moves the focused row's node to its new place, the browser drops focus;
    // put it back on the same button (its name now has the new position).
    const direction = to < from ? "up" : "down";
    const label = `Move ${blockName(block)} block ${to + 1} ${direction}`;
    requestAnimationFrame(() => {
      if (document.activeElement && document.activeElement !== document.body) return;
      document.querySelector<HTMLElement>(`button[aria-label="${CSS.escape(label)}"]`)?.focus();
    });
  }

  function add(type: BlockType) {
    const block = emptyBlock(type);
    const at = selectedIndex >= 0 ? selectedIndex + 1 : blocks.length;
    const next = [...blocks.slice(0, at), block, ...blocks.slice(at)];
    onChange(next);
    onSelect(block.key);
    setPaletteOpen(false);
    announce(`${BLOCK_TYPES[type].name} block added at position ${at + 1} of ${next.length}.`);
    setFocusSettings((n) => n + 1);
  }

  function confirmDelete() {
    if (!deleting) return;
    const index = blocks.findIndex((block) => block.key === deleting.key);
    const next = blocks.filter((block) => block.key !== deleting.key);
    onChange(next);
    const neighbour = next[Math.min(index, next.length - 1)] ?? null;
    onSelect(neighbour?.key ?? null);
    announce(`${blockName(deleting)} block deleted. Save the draft to keep this change.`);
    setDeleting(null);
    requestAnimationFrame(() =>
      document.getElementById(neighbour ? selectId(neighbour.key) : "blocks-add")?.focus(),
    );
  }

  return (
    <div className="flex flex-wrap items-start gap-5">
      <section
        aria-labelledby="blocks-title"
        className="flex min-w-0 flex-[1_1_280px] flex-col gap-3 rounded-card border border-line bg-noir-800 p-4 xl:max-w-[340px]"
      >
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="blocks-title" className="text-[17px] font-bold">
            Blocks
          </h2>
          <span className="text-caption text-muted">
            {shown} of {blocks.length} shown
          </span>
        </div>
        {blocks.length === 0 ? (
          <EmptyState title="No blocks yet.">
            <p className="text-small">
              {canWrite ? "Add the first one with + Add block." : "An editor adds them."}
            </p>
          </EmptyState>
        ) : (
          <ol aria-label="Blocks in page order" className="flex flex-col gap-2">
            {blocks.map((block, index) => {
              const isSelected = block.key === selectedKey;
              const problems = Object.keys(errors.get(block.key) ?? {}).length > 0;
              return (
                <li
                  key={block.key}
                  className={cx(
                    "flex flex-col gap-1.5 rounded-tile border p-2",
                    isSelected ? "border-gold-500 bg-gold-tint" : "border-line bg-noir-900",
                  )}
                >
                  <button
                    id={selectId(block.key)}
                    type="button"
                    aria-pressed={isSelected}
                    onClick={() => onSelect(block.key)}
                    className="flex min-h-11 flex-col items-start rounded-tag px-2 py-1 text-left"
                  >
                    <span
                      className={cx(
                        "text-small font-bold",
                        isSelected
                          ? "text-gold-300"
                          : block.is_visible
                            ? "text-ivory"
                            : "text-muted",
                      )}
                    >
                      {index + 1}. {blockName(block)}
                    </span>{" "}
                    <span className="text-xs [overflow-wrap:anywhere] text-muted">
                      {blockCaption(block)}
                    </span>
                    {problems ? (
                      <span className="text-xs font-bold text-danger"> Needs attention</span>
                    ) : null}
                  </button>
                  {canWrite ? (
                    <div className="flex flex-wrap items-center justify-between gap-1 px-1">
                      <Switch
                        checked={block.is_visible}
                        onChange={(visible) => {
                          update({ ...block, is_visible: visible });
                          announce(
                            `${blockName(block)} ${visible ? "shown" : "hidden"} on the website. Save the draft to keep this change.`,
                          );
                        }}
                        label="Show on website"
                        stateText={{ on: "Shown", off: "Hidden" }}
                        context={`${blockName(block)}, block ${index + 1}`}
                      />
                      <ReorderButtons
                        index={index}
                        count={blocks.length}
                        itemLabel={`${blockName(block)} block ${index + 1}`}
                        onMove={move}
                      />
                    </div>
                  ) : (
                    <span className="px-2 text-xs text-muted">
                      {block.is_visible ? "Shown on the website" : "Hidden"}
                    </span>
                  )}
                </li>
              );
            })}
          </ol>
        )}
        {canWrite ? (
          <Button id="blocks-add" variant="secondary" onClick={() => setPaletteOpen(true)}>
            + Add block
          </Button>
        ) : null}
        <p className="text-caption text-muted">
          Use Move up and Move down to change the order. Numbers and Testimonials stay hidden on the
          website until real, checked data is entered.
        </p>
      </section>

      {selected ? (
        <>
          <section
            aria-label="Preview"
            className="flex min-w-0 flex-[2_1_360px] flex-col gap-3 rounded-card border border-line bg-noir-800 p-4"
          >
            <SegmentedControl
              label="Preview size"
              value={previewSize}
              options={[
                { value: "desktop", label: "Desktop" },
                { value: "mobile", label: "Mobile" },
              ]}
              onChange={setPreviewSize}
              className="self-end"
            />
            <BlockPreview
              block={selected}
              position={selectedIndex + 1}
              count={blocks.length}
              size={previewSize}
            />
          </section>
          <section
            aria-labelledby="block-settings-title"
            className="flex min-w-0 flex-[2_1_340px] flex-col gap-4 rounded-card border border-gold-line-strong bg-noir-800 p-4"
          >
            <div>
              <p className="text-xs font-bold tracking-[0.12em] text-muted">BLOCK SETTINGS</p>
              <h2
                id="block-settings-title"
                ref={settingsHeading}
                tabIndex={-1}
                className="text-[17px] font-bold"
              >
                {blockName(selected)} · block {selectedIndex + 1}
              </h2>
              <p className="text-caption text-muted">{BLOCK_TYPES[selected.type].description}</p>
            </div>
            {errors.get(selected.key)?.[""] ? (
              <Alert tone="error">{errors.get(selected.key)?.[""]}</Alert>
            ) : null}
            <fieldset disabled={!canWrite} className="flex min-w-0 flex-col gap-4">
              <legend className="sr-only">{blockName(selected)} settings</legend>
              <BlockForm
                key={selected.key}
                block={selected}
                onChange={update}
                errors={errors.get(selected.key) ?? {}}
                canUpload={canUpload && canWrite}
                onBusyChange={onBusyChange}
              />
            </fieldset>
            {canWrite ? (
              <Button
                variant="danger"
                className="self-start"
                aria-label={`Delete block ${selectedIndex + 1}: ${blockName(selected)}`}
                onClick={() => setDeleting(selected)}
              >
                Delete block
              </Button>
            ) : null}
            <p className="text-caption text-muted">
              Changes are kept as a draft until you save. Publishing puts the saved version on the
              website; every publish is in the audit log.
            </p>
          </section>
        </>
      ) : null}

      <Dialog
        open={paletteOpen}
        wide
        title="Add a block"
        onSubmit={() => undefined}
        onClose={() => setPaletteOpen(false)}
        footer={
          <Button variant="secondary" onClick={() => setPaletteOpen(false)}>
            Cancel
          </Button>
        }
      >
        <p className="text-small text-muted">
          {selected
            ? `The new block goes after “${blockName(selected)}” (block ${selectedIndex + 1}).`
            : "The new block goes at the end of the page."}
        </p>
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-2">
          {BLOCK_TYPE_ORDER.map((type, index) => (
            <li key={type}>
              <button
                type="button"
                data-autofocus={index === 0 ? true : undefined}
                onClick={() => add(type)}
                className="flex min-h-11 w-full flex-col items-start gap-0.5 rounded-tile border border-line bg-noir-900 px-3 py-2.5 text-left hover:border-gold-500"
              >
                <span className="text-small font-bold text-ivory">{BLOCK_TYPES[type].name}</span>{" "}
                <span className="text-xs text-muted">{BLOCK_TYPES[type].description}</span>
              </button>
            </li>
          ))}
        </ul>
      </Dialog>

      <ConfirmDialog
        open={deleting !== null}
        title={deleting ? `Delete this ${blockName(deleting)} block?` : "Delete this block?"}
        confirmLabel="Delete block"
        tone="danger"
        onCancel={() => setDeleting(null)}
        onConfirm={confirmDelete}
      >
        It is removed from the page when you save the draft. To keep it but not show it, use
        &ldquo;Show on website&rdquo; instead.
      </ConfirmDialog>
    </div>
  );
}
