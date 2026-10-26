/**
 * Words the CMS shows for the content module's enum values (page kinds, offer placements and
 * states, redirect codes, lead-form sources), in the boards' wording (NoirCmsPage,
 * NoirCmsContent). Keys are typed from the generated client, so a new or renamed value fails the
 * type-check here instead of showing a raw key on screen.
 */
import type { ChipVariant } from "@empire/ui";
import type { Schema } from "@/lib/api";

export type PageKind = Schema<"Page">["kind"];
export type OfferPlacement = Schema<"Offer">["placement"];
export type OfferState = Schema<"Offer">["state"];
export type RedirectCode = Schema<"Redirect">["status_code"];

export const PAGE_KIND: Record<PageKind, string> = {
  standard: "Standard",
  landing: "Campaign landing page",
  legal: "Legal",
  system: "System",
};

/** What each kind is for, under the Kind choice. */
export const PAGE_KIND_HELP: Record<PageKind, string> = {
  standard: "An ordinary page, e.g. NRI buyers or careers.",
  landing: "A campaign page for ads; can be hidden from search engines.",
  legal: "Privacy policy, terms, disclaimer. Publishing needs the legal.publish permission.",
  system: "Comes with the site (home, about, contact, projects); can't be deleted or renamed.",
};

export const OFFER_PLACEMENT: Record<OfferPlacement, string> = {
  banner: "Site-wide banner",
  home: "Home page",
  project: "Project page",
};

export const OFFER_STATE: Record<OfferState, string> = {
  scheduled: "Scheduled",
  live: "Live",
  ended: "Ended",
  inactive: "Inactive",
};

export const OFFER_STATE_CHIP: Record<OfferState, ChipVariant> = {
  scheduled: "scheduled",
  live: "published",
  ended: "archived",
  inactive: "draft",
};

/** What each state means, for the chip's neighbour text and the editor. */
export const OFFER_STATE_HELP: Record<OfferState, string> = {
  scheduled: "Starts on its own on the start date.",
  live: "Showing on the website now.",
  ended: "Past its end date; kept for the record.",
  inactive: "Switched off; not shown whatever the dates.",
};

export const REDIRECT_CODE: Record<RedirectCode, string> = {
  "301": "301 · moved permanently",
  "308": "308 · moved permanently (keeps the method)",
};
