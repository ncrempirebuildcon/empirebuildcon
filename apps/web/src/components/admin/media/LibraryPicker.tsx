"use client";
/**
 * "Choose from the library": a dialog listing the media library's photos (or videos) as
 * thumbnails to pick one, or several for a gallery. Used by the content screens' media fields
 * (MediaField.tsx): a block's image, a post cover, an offer image, a testimonial photo.
 *
 * How it works:
 *   1. The list is `GET /admin/media?kind=…&q=…&page=…` (24 a page), the same query as the
 *      library screen. Typing in Search waits 300 ms, then loads; Enter in Search searches
 *      instead of submitting the dialog.
 *   2. Choices are native radio buttons (one) or checkboxes (several) inside a fieldset, so arrow
 *      keys, Space and screen readers work as everywhere else. Each thumbnail's alt text (alt
 *      text, else title) and the visible title name the choice.
 *   3. "Use this photo" hands the chosen items back; Cancel or Escape changes nothing.
 *   Choosing never attaches anything: the caller saves the id with its own form.
 */
import { useEffect, useState } from "react";
import { Alert, Button, Dialog, TextField, cx } from "@empire/ui";
import { api, call } from "@/lib/api";
import { honestLabelText } from "@/lib/media/labels";
import type { Media } from "@/lib/media/upload";
import { problemMessage } from "@/lib/problems";
import { useLoad } from "@/components/admin/useLoad";
import { MediaThumb } from "./MediaThumb";

const PER_PAGE = 24;

export type PickableKind = "image" | "video";

const NOUN: Record<PickableKind, { one: string; many: string }> = {
  image: { one: "photo", many: "photos" },
  video: { one: "video", many: "videos" },
};

export interface LibraryPickerProps {
  open: boolean;
  kind: PickableKind;
  /** Pick several (a gallery) instead of one. */
  multiple?: boolean;
  /** Most items that may be picked at once when `multiple`. */
  max?: number;
  /** Ids already chosen, ticked when the dialog opens. */
  chosenIds?: readonly string[];
  onPick: (items: Media[]) => void;
  onClose: () => void;
}

export function LibraryPicker(props: LibraryPickerProps) {
  // WHY a keyed body: the search and ticks start fresh every time the dialog opens.
  return (
    <Dialog
      open={props.open}
      wide
      title={`Choose ${props.multiple ? NOUN[props.kind].many : `a ${NOUN[props.kind].one}`} from the library`}
      onSubmit={() => undefined}
      onClose={props.onClose}
      footer={null}
    >
      {props.open ? <PickerBody {...props} /> : null}
    </Dialog>
  );
}

function PickerBody({
  kind,
  multiple = false,
  max = 24,
  chosenIds = [],
  onPick,
  onClose,
}: LibraryPickerProps) {
  const [typed, setTyped] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [picked, setPicked] = useState<Map<string, Media>>(() => new Map());
  // One choice: starts on the current item. Several: only new ticks (the gallery adds them).
  const [ticked, setTicked] = useState<Set<string>>(() =>
    multiple ? new Set() : new Set(chosenIds.slice(0, 1)),
  );
  const [problem, setProblem] = useState<string | null>(null);
  const already = new Set(multiple ? chosenIds : []);
  const noun = NOUN[kind];

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(typed.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [typed]);

  const list = useLoad(`library-picker:${kind}:${query}:${page}`, () =>
    call(
      api.GET("/api/v1/admin/media", {
        params: { query: { kind, q: query || undefined, page, per_page: PER_PAGE } },
      }),
    ),
  );
  const items = list.data?.items ?? [];
  const pages = list.data?.meta.pages ?? 1;

  function toggle(media: Media, on: boolean) {
    setProblem(null);
    setPicked((current) => new Map(current).set(media.id, media));
    setTicked((current) => {
      const next = multiple ? new Set(current) : new Set<string>();
      if (on) next.add(media.id);
      else next.delete(media.id);
      return next;
    });
  }

  function use() {
    const chosen = [...ticked]
      .map((id) => picked.get(id))
      .filter((media): media is Media => media !== undefined);
    if (chosen.length === 0) {
      // Nothing new chosen: the current choice stands (one), or there is nothing to add.
      if (!multiple && ticked.size > 0) onClose();
      else setProblem(`Choose a ${noun.one} first.`);
      return;
    }
    if (multiple && chosen.length + already.size > max) {
      setProblem(`A gallery holds at most ${max} ${noun.many}; ${already.size} are already in it.`);
      return;
    }
    onPick(chosen);
  }

  const count = ticked.size;

  return (
    <>
      <TextField
        label="Search"
        type="search"
        placeholder="Title or alt text"
        value={typed}
        maxLength={100}
        onChange={(event) => setTyped(event.target.value)}
        onKeyDown={(event) => {
          // WHY: Enter in a dialog field submits the dialog; here it should only search.
          if (event.key === "Enter") {
            event.preventDefault();
            setQuery(typed.trim());
            setPage(1);
          }
        }}
      />
      {list.error ? (
        <Alert tone="error">{problemMessage(list.error, "Couldn't load the library.")}</Alert>
      ) : null}
      <fieldset aria-busy={list.loading || undefined} className="flex min-w-0 flex-col gap-2">
        <legend className="mb-1 text-small font-semibold text-ivory">
          {noun.many.charAt(0).toUpperCase() + noun.many.slice(1)} in the library
          {multiple ? ` (up to ${max})` : ""}
        </legend>
        {list.loading && !list.data ? (
          <p className="text-caption text-muted" role="status">
            Loading the library…
          </p>
        ) : items.length === 0 ? (
          <p className="text-caption text-muted">
            {query
              ? `No ${noun.many} match “${query}”.`
              : `No ${noun.many} in the library yet. Upload one instead.`}
          </p>
        ) : (
          <ul className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-2.5">
            {items.map((media) => {
              const isAlready = already.has(media.id);
              const on = isAlready || ticked.has(media.id);
              const label = honestLabelText(media.label, media.label_month);
              return (
                <li key={media.id}>
                  <label
                    className={cx(
                      "relative flex cursor-pointer flex-col gap-1 rounded-tag border-2 p-1",
                      on ? "border-gold-400 bg-gold-tint" : "border-transparent",
                    )}
                  >
                    <input
                      type={multiple ? "checkbox" : "radio"}
                      name="library-picker"
                      value={media.id}
                      checked={on}
                      disabled={isAlready}
                      onChange={(event) => toggle(media, event.target.checked)}
                      className="peer sr-only"
                    />
                    <MediaThumb media={media} shape={kind === "video" ? "video" : "photo"} />{" "}
                    <span className="truncate text-xs font-semibold text-ivory">{media.title}</span>{" "}
                    <span className="text-xs text-muted">
                      {label ?? (kind === "image" ? "No label yet" : media.format.toUpperCase())}
                      {media.is_sample ? " · Sample" : ""}
                      {isAlready ? " · Already added" : ""}
                    </span>
                    {/* The focus ring for the hidden input, drawn on the whole card. */}
                    <span
                      aria-hidden="true"
                      className="pointer-events-none absolute inset-0 rounded-tag peer-focus-visible:outline-2 peer-focus-visible:outline-gold-300"
                    />
                  </label>
                </li>
              );
            })}
          </ul>
        )}
      </fieldset>
      {pages > 1 ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            disabled={page <= 1 || list.loading}
            onClick={() => setPage((n) => Math.max(1, n - 1))}
          >
            Previous
          </Button>
          <span className="text-caption text-muted">
            Page {page} of {pages}
          </span>
          <Button
            variant="secondary"
            disabled={page >= pages || list.loading}
            onClick={() => setPage((n) => Math.min(pages, n + 1))}
          >
            Next
          </Button>
        </div>
      ) : null}
      {problem ? <Alert tone="error">{problem}</Alert> : null}
      <div className="flex flex-wrap justify-end gap-3">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={use}>
          {multiple
            ? count > 0
              ? `Add ${count} ${count === 1 ? noun.one : noun.many}`
              : `Add ${noun.many}`
            : `Use this ${noun.one}`}
        </Button>
      </div>
    </>
  );
}
