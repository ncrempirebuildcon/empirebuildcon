"use client";
/**
 * The bar at the top of the page and post editors (board NoirCmsPage: "Draft changes · Last
 * saved … · Save draft · Publish"): the SAMPLE and state chips, whether everything is saved (in
 * words), when and by whom it was last saved, and the Save / Publish / Unpublish buttons.
 * Plus `SampleNote`, the "nothing here is shown on the live site" line for sample rows (D-015).
 *
 * The caller decides which buttons show (by permission and state); the API checks again.
 */
import { Button, Chip } from "@empire/ui";
import { PUBLISH_STATE, PUBLISH_STATE_CHIP, type PublishState } from "@/lib/labels";

export interface EditorStatusBarProps {
  isSample: boolean;
  state: PublishState;
  /** The state chip's words, when not the state's own ("New draft"). */
  stateLabel?: string;
  dirty: boolean;
  /** "Legal · /privacy · last saved 24 Oct 2026, 4:10 pm by E2E Admin" */
  meta: string | null;
  /** Shown with `content.write`. */
  save: { onClick: () => void; busy: boolean; disabled: boolean } | null;
  /** Shown with the publish permission, on a draft. */
  publish: { onClick: () => void; busy: boolean; disabled: boolean; describedBy: string } | null;
  /** Shown with the publish permission, on a live item. */
  unpublish: { onClick: () => void; busy: boolean } | null;
}

export function EditorStatusBar({
  isSample,
  state,
  stateLabel,
  dirty,
  meta,
  save,
  publish,
  unpublish,
}: EditorStatusBarProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3.5 rounded-card border border-line bg-noir-800 px-4 py-3">
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          {isSample ? <Chip variant="sample">SAMPLE</Chip> : null}
          <Chip variant={PUBLISH_STATE_CHIP[state]}>{stateLabel ?? PUBLISH_STATE[state]}</Chip>
          <span className="text-small font-bold text-ivory">
            {dirty ? "Unsaved changes" : "All changes saved"}
          </span>
        </div>
        {meta ? <span className="text-caption text-muted">{meta}</span> : null}
      </div>
      <div className="flex flex-wrap items-center gap-2.5">
        {save ? (
          <Button
            variant="secondary"
            loading={save.busy}
            disabled={save.disabled}
            onClick={save.onClick}
          >
            {state === "draft" ? "Save draft" : "Save changes"}
          </Button>
        ) : null}
        {unpublish && state === "published" ? (
          <Button variant="secondary" loading={unpublish.busy} onClick={unpublish.onClick}>
            Unpublish
          </Button>
        ) : null}
        {publish && state === "draft" ? (
          <Button
            loading={publish.busy}
            disabled={publish.disabled}
            aria-describedby={publish.describedBy}
            onClick={publish.onClick}
          >
            Publish
          </Button>
        ) : null}
      </div>
    </div>
  );
}

/** The sample-data line (D-015): shown on sample rows, in words and with a red dot. */
export function SampleNote() {
  return (
    <div
      role="note"
      className="flex items-center gap-2.5 rounded-tile border border-danger/60 bg-noir-700 px-4 py-2 text-caption"
    >
      <span aria-hidden="true" className="size-2 shrink-0 rounded-pill bg-danger" />
      Sample data · nothing here is shown on the live site
    </div>
  );
}
