/**
 * The page editor's blocks while they are being edited: the API's `BlockInput` union (one
 * variant per block type, `data` typed per type, decision D-035) plus a local `key`, so new
 * blocks without an id can be selected, moved and announced like saved ones.
 *
 * How it works:
 *   1. `toDrafts` turns the saved blocks into drafts; `toInputs` turns drafts back into the body
 *      of `PUT /pages/{id}/blocks` (the full ordered list, saved in one transaction).
 *   2. `emptyBlock(type)` makes a new block with every field at its default (the generated types
 *      require fields that have defaults, so they are all written out).
 *   3. `checkBlock` repeats the API's rules that staff hit most (a heading, a stat's source and
 *      date, a safe link), so problems show next to the field before saving. The API stays the
 *      guard and checks everything again (blocks.py).
 *   4. `blockErrors` sorts the API's field errors ("blocks.3.data.items.0.source") by block.
 */
import { istToday } from "@empire/ui/format";
import type { Schema } from "@/lib/api";
import type { BlockType } from "@/lib/content/blockTypes";
import { BLOCK_TYPES } from "@/lib/content/blockTypes";
import { linkProblem } from "@/lib/content/links";
import type { FieldErrors } from "@/lib/problems";

export type BlockInput = Schema<"BlockInput">;
export type SavedBlock = Schema<"Block">;
export type BlockOf<T extends BlockType> = Extract<BlockInput, { type: T }>;
export type DataOf<T extends BlockType> = BlockOf<T>["data"];

/** A block in the editor: the API's input shape plus a key that never changes. */
export type DraftBlock = BlockInput & { key: string };

let counter = 0;
/** A key for a block that has no id yet. */
export function newKey(): string {
  counter += 1;
  return `new-${Date.now().toString(36)}-${counter}`;
}

export function toDrafts(blocks: readonly SavedBlock[] | null | undefined): DraftBlock[] {
  return [...(blocks ?? [])]
    .sort((a, b) => a.sort_order - b.sort_order)
    .map(
      (block) =>
        ({
          key: block.id,
          id: block.id,
          type: block.type,
          data: block.data,
          is_visible: block.is_visible,
        }) as DraftBlock,
    );
}

export function toInputs(drafts: readonly DraftBlock[]): BlockInput[] {
  return drafts.map((draft) => {
    const input = {
      id: draft.id,
      type: draft.type,
      data: draft.data,
      is_visible: draft.is_visible,
    } as BlockInput;
    if (input.type !== "video") return input;
    // WHY strip read-only fields: the video block returns `provider` and `video_id` worked out
    // from the link; the API's strict models refuse them on input.
    const data = Object.fromEntries(
      Object.entries(input.data).filter(([name]) => name !== "provider" && name !== "video_id"),
    ) as typeof input.data;
    return { ...input, data };
  });
}

const cta = () => null;

/** A new block of `type`, every field at its default. */
export function emptyBlock(type: BlockType): DraftBlock {
  const base = { key: newKey(), id: null, is_visible: true };
  switch (type) {
    case "hero":
      return {
        ...base,
        type,
        data: {
          eyebrow: null,
          heading: "",
          subheading: null,
          image_id: null,
          cta: cta(),
          secondary_cta: cta(),
        },
      };
    case "rich_text":
      return { ...base, type, data: { heading: null, body: "" } };
    case "image":
      return { ...base, type, data: { image_id: "", caption: null } };
    case "gallery":
      return { ...base, type, data: { heading: null, image_ids: [] } };
    case "video":
      return { ...base, type, data: { heading: null, caption: null, media_id: null, url: null } };
    case "project_grid":
    case "property_grid":
      return {
        ...base,
        type,
        data: {
          heading: null,
          status: null,
          city_id: null,
          featured_only: false,
          limit: 6,
          show_status_tabs: false,
        },
      };
    case "cta":
      return { ...base, type, data: { heading: null, text: null, label: "", href: "" } };
    case "lead_form":
      return {
        ...base,
        type,
        data: { heading: null, intro: null, source: "contact_form", project_id: null },
      };
    case "faq_list":
      return { ...base, type, data: { heading: null, project_id: null, faq_ids: [] } };
    case "stats":
      return {
        ...base,
        type,
        data: { heading: null, items: [emptyStat()], note: null },
      };
    case "testimonials":
      return {
        ...base,
        type,
        data: { heading: null, testimonial_ids: [], project_id: null, limit: 3 },
      };
    case "offer_banner":
      return { ...base, type, data: { offer_id: null, placement: "banner" } };
    case "map":
      return { ...base, type, data: { heading: null, project_id: "" } };
    case "steps":
      return { ...base, type, data: { heading: null, items: [{ title: "", text: null }] } };
    case "columns":
      return {
        ...base,
        type,
        data: {
          heading: null,
          columns: [
            { heading: null, body: "" },
            { heading: null, body: "" },
          ],
        },
      };
    case "divider":
      return { ...base, type, data: {} };
  }
}

export function emptyStat(): DataOf<"stats">["items"][number] {
  return { value: "", label: "", source: "", as_of: "" };
}

/** The block's name in the list. */
export const blockName = (block: Pick<DraftBlock, "type">) => BLOCK_TYPES[block.type].name;

/**
 * The note for a FAQs or testimonials block that is hidden and picks nothing, or null.
 *
 * WHY (review M4): when the last FAQ or testimonial a block picked is deleted, the API hides the
 * block instead of letting it widen to every site-wide FAQ or the newest testimonials of any
 * project. A block in that state looks like "Site-wide" / "Newest" in its form, so the editor
 * says what showing it would do. (Someone may also have hidden such a block on purpose, so the
 * note doesn't claim a delete happened.)
 */
export function emptyPickNote(block: DraftBlock): string | null {
  if (block.is_visible !== false) return null;
  if (
    block.type === "faq_list" &&
    (block.data.faq_ids ?? []).length === 0 &&
    !block.data.project_id
  )
    return "Hidden, and no FAQs are picked. This happens when the FAQs it showed are deleted. Shown like this, it would list every site-wide FAQ: pick FAQs again or choose a project, then show it.";
  if (
    block.type === "testimonials" &&
    (block.data.testimonial_ids ?? []).length === 0 &&
    !block.data.project_id
  )
    return "Hidden, and no testimonials are picked. This happens when the ones it showed are deleted. Shown like this, it would show the newest testimonials from any project: pick again or choose a project, then show it.";
  return null;
}

/** A short line under the name in the block list: the heading or the first words. */
export function blockCaption(block: DraftBlock): string {
  if (emptyPickNote(block)) return "Hidden · nothing picked";
  const short = (text: string | null | undefined, empty: string) => {
    const value = (text ?? "").replace(/\s+/g, " ").trim();
    if (!value) return empty;
    return value.length > 48 ? `${value.slice(0, 47)}…` : value;
  };
  switch (block.type) {
    case "hero":
      return short(block.data.heading, "No heading yet");
    case "rich_text":
      return short(block.data.heading ?? block.data.body.replace(/[*_]/g, ""), "No text yet");
    case "image":
      return block.data.image_id ? short(block.data.caption, "Photo chosen") : "No photo yet";
    case "gallery":
      return `${block.data.image_ids.length} photo${block.data.image_ids.length === 1 ? "" : "s"}`;
    case "video":
      return block.data.url
        ? "YouTube or Vimeo link"
        : block.data.media_id
          ? "Video from the library"
          : "No video yet";
    case "project_grid":
    case "property_grid":
      return short(block.data.heading, `Up to ${block.data.limit} cards`);
    case "cta":
      return short(block.data.label, "No button text yet");
    case "lead_form":
      return short(block.data.heading, "Enquiry form");
    case "faq_list":
      return (block.data.faq_ids ?? []).length > 0
        ? `${(block.data.faq_ids ?? []).length} chosen FAQs`
        : block.data.project_id
          ? "A project's FAQs"
          : "Site-wide FAQs";
    case "stats":
      return `${block.data.items.length} number${block.data.items.length === 1 ? "" : "s"} · each with a source`;
    case "testimonials":
      return (block.data.testimonial_ids ?? []).length > 0
        ? `${(block.data.testimonial_ids ?? []).length} chosen`
        : "Shown only when real ones exist";
    case "offer_banner":
      return block.data.offer_id ? "One chosen offer" : "Live offer for its placement";
    case "map":
      return block.data.project_id ? "Project location" : "No project yet";
    case "steps":
      return `${block.data.items.length} step${block.data.items.length === 1 ? "" : "s"}`;
    case "columns":
      return `${block.data.columns.length} columns`;
    case "divider":
      return "A thin line";
  }
}

/** Problems with one button (label + link); `prefix` is the field path, e.g. "cta". */
function checkButton(
  out: FieldErrors,
  prefix: string,
  button: { label: string; href: string } | null | undefined,
  required: boolean,
) {
  const label = button?.label.trim() ?? "";
  const href = button?.href.trim() ?? "";
  if (!required && !label && !href) return;
  if (!label) out[`${prefix}.label`] = "Enter the button text.";
  if (!href) out[`${prefix}.href`] = "Enter where the button goes, e.g. /contact.";
  else {
    const problem = linkProblem(href);
    if (problem) out[`${prefix}.href`] = problem;
  }
}

/**
 * The problems the editor can see without the API, keyed by the path inside `data`
 * ("heading", "items.0.source"); "" is a problem with the whole block.
 */
export function checkBlock(block: DraftBlock): FieldErrors {
  const out: FieldErrors = {};
  switch (block.type) {
    case "hero":
      if (!block.data.heading.trim()) out.heading = "Enter the heading.";
      checkButton(out, "cta", block.data.cta, false);
      checkButton(out, "secondary_cta", block.data.secondary_cta, false);
      break;
    case "rich_text":
      if (!block.data.body.trim()) out.body = "Enter the text.";
      break;
    case "image":
      if (!block.data.image_id) out.image_id = "Choose a photo.";
      break;
    case "gallery":
      if (block.data.image_ids.length === 0) out.image_ids = "Add at least one photo.";
      break;
    case "video":
      if (!block.data.media_id && !block.data.url?.trim()) {
        out[""] = "Choose a video from the library or paste a YouTube or Vimeo link.";
      }
      break;
    case "cta":
      checkButton(out, "", { label: block.data.label, href: block.data.href }, true);
      // The button's fields sit on the block itself, so drop the leading dot.
      for (const key of [".label", ".href"]) {
        if (out[key]) {
          out[key.slice(1)] = out[key] as string;
          delete out[key];
        }
      }
      break;
    case "stats": {
      const today = istToday();
      block.data.items.forEach((item, index) => {
        // COMPLIANCE: a number on the website must say where it comes from and when it was true.
        if (!item.value.trim()) out[`items.${index}.value`] = "Enter the number.";
        if (!item.label.trim()) out[`items.${index}.label`] = "Say what the number counts.";
        if (!item.source.trim()) {
          out[`items.${index}.source`] = "Say where this number comes from.";
        }
        if (!item.as_of) out[`items.${index}.as_of`] = "Enter the date the number was true.";
        else if (item.as_of > today) {
          out[`items.${index}.as_of`] = "The date can't be in the future.";
        }
      });
      break;
    }
    case "map":
      if (!block.data.project_id) out.project_id = "Choose the project.";
      break;
    case "steps":
      block.data.items.forEach((item, index) => {
        if (!item.title.trim()) out[`items.${index}.title`] = "Enter the step's title.";
      });
      break;
    case "columns":
      block.data.columns.forEach((column, index) => {
        if (!column.body.trim()) out[`columns.${index}.body`] = "Enter the column's text.";
      });
      break;
    case "offer_banner":
      if (!block.data.offer_id && !block.data.placement)
        out[""] = "Choose an offer or a placement.";
      break;
    default:
      break;
  }
  return out;
}

/**
 * The API's errors for `PUT /pages/{id}/blocks`, by block index, with paths inside `data`.
 * Paths arrive as "blocks.2.data.items.0.source"; some validators name the block type too
 * ("blocks.2.stats.data.items.0.source"), and a whole-block problem ends at "data" or the index.
 */
export function blockErrors(errors: FieldErrors): Map<number, FieldErrors> {
  const out = new Map<number, FieldErrors>();
  for (const [field, message] of Object.entries(errors)) {
    const [head, position, ...rest] = field.split(".");
    if (head !== "blocks" || !position || !/^\d+$/.test(position)) continue;
    if (rest[0] && rest[0] in BLOCK_TYPES && rest[1] === "data") rest.shift();
    if (rest[0] === "data") rest.shift();
    const index = Number(position);
    const path = rest.join(".");
    const entry = out.get(index) ?? {};
    entry[path] ??= message;
    out.set(index, entry);
  }
  return out;
}
