/**
 * The page block types as staff see them: the name and one-line description in the "Add a
 * block" palette (board NoirCmsPage), in palette order. The API validates each type's `data`
 * (spec Phase 4 part 4 §2); the forms live in app/admin/pages/[id]/blocks/.
 *
 * Keys are the API's block types; `satisfies` makes a new or renamed type fail the type-check
 * here instead of showing a raw key on screen.
 */
import type { Schema } from "@/lib/api";

export type BlockType = Schema<"BlockInput">["type"];

export interface BlockTypeInfo {
  /** Name in the palette and the block list, e.g. "Hero". */
  name: string;
  /** What it is for, in one line. */
  description: string;
}

export const BLOCK_TYPES = {
  hero: {
    name: "Hero",
    description: "Big heading, a short intro, an image and a button. Usually the first block.",
  },
  rich_text: {
    name: "Text",
    description: "Paragraphs and bullets, with *bold* and _italic_.",
  },
  image: { name: "Image", description: "One photo from the library, with a caption." },
  gallery: { name: "Gallery", description: "Up to 24 photos from the library, in your order." },
  video: {
    name: "Video",
    description: "A video from the library, or a YouTube or Vimeo link.",
  },
  project_grid: {
    name: "Project cards",
    description: "Projects filtered by status, city or featured, up to 24 cards.",
  },
  property_grid: {
    name: "Property cards",
    description: "Flats, villas and plots (configurations) with the same filters.",
  },
  cta: {
    name: "Call to action",
    description: "One line and a button to a page on this site or a secure https link.",
  },
  lead_form: {
    name: "Enquiry form",
    description: "Name and mobile with the consent boxes; enquiries go to the leads inbox.",
  },
  faq_list: {
    name: "FAQs",
    description: "Questions and answers: a project's FAQs, or ones you choose.",
  },
  stats: {
    name: "Numbers",
    description: "Real figures only, each with where it comes from and the date it was true.",
  },
  testimonials: {
    name: "Testimonials",
    description: "Real buyers' words with a recorded source and permission.",
  },
  offer_banner: {
    name: "Offer banner",
    description: "One offer, or whichever offer is live for its placement.",
  },
  map: { name: "Map", description: "A project's location pin, with directions." },
  steps: { name: "Steps", description: "Up to 8 numbered steps, e.g. how a site visit works." },
  columns: { name: "Columns", description: "Two or three columns of formatted text." },
  divider: { name: "Divider", description: "A thin gold line between two sections." },
} as const satisfies Record<BlockType, BlockTypeInfo>;

/** Block types in palette order. */
export const BLOCK_TYPE_ORDER = Object.keys(BLOCK_TYPES) as BlockType[];
