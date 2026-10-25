/**
 * The offer editor's fields, converted from the API's `Offer` and back into the create body
 * (`OfferInput`) or the PATCH body (`OfferUpdate`, changed fields only), plus the checks staff
 * hit most (dates in order, a button needs text and a link, the honesty rules in
 * lib/content/offers.ts). The API checks everything again.
 */
import type { Schema } from "@/lib/api";
import type { OfferPlacement } from "@/lib/content/labels";
import { linkProblem } from "@/lib/content/links";
import { NO_URGENCY, TERMS_NEEDED, hasUrgency, mentionsMoney } from "@/lib/content/offers";
import {
  fromInstant,
  toInstant,
  type IstDateTime,
  type ScheduleProblem,
} from "@/lib/content/schedule";
import type { Media } from "@/lib/media/upload";
import type { FieldErrors } from "@/lib/problems";

export type Offer = Schema<"Offer">;
export type OfferInput = Schema<"OfferInput">;
export type OfferUpdate = Schema<"OfferUpdate">;

export interface OfferForm {
  title: string;
  body: string;
  image: Media | null;
  cta_label: string;
  cta_url: string;
  terms: string;
  terms_url: string;
  project_id: string;
  placement: OfferPlacement;
  starts: IstDateTime;
  ends: IstDateTime;
  is_active: boolean;
  priority: number | null;
}

export const EMPTY_OFFER: OfferForm = {
  title: "",
  body: "",
  image: null,
  cta_label: "",
  cta_url: "",
  terms: "",
  terms_url: "",
  project_id: "",
  placement: "banner",
  starts: { date: "", time: "" },
  ends: { date: "", time: "" },
  is_active: false,
  priority: 0,
};

export function toForm(offer: Offer): OfferForm {
  return {
    title: offer.title,
    body: offer.body ?? "",
    image: offer.image ?? null,
    cta_label: offer.cta_label ?? "",
    cta_url: offer.cta_url ?? "",
    terms: offer.terms ?? "",
    terms_url: offer.terms_url ?? "",
    project_id: offer.project_id ?? "",
    placement: offer.placement,
    starts: fromInstant(offer.starts_at),
    ends: fromInstant(offer.ends_at),
    is_active: offer.is_active,
    priority: offer.priority,
  };
}

const orNull = (value: string) => (value.trim() === "" ? null : value.trim());
// WHY default times: a start typed without a time starts that morning, an end lasts the day.
const startOf = (value: IstDateTime) => toInstant(value, "00:00");
const endOf = (value: IstDateTime) => toInstant(value, "23:59");

export interface OfferProblems {
  fields: FieldErrors;
  starts: ScheduleProblem | null;
  ends: ScheduleProblem | null;
}

export function checkForm(form: OfferForm): OfferProblems {
  const fields: FieldErrors = {};
  if (!form.title.trim()) fields.title = "Enter the offer's name.";
  if (form.placement === "project" && !form.project_id) {
    fields.project_id = "Choose the project whose page shows this offer.";
  }
  if (form.cta_label.trim() && !form.cta_url.trim())
    fields.cta_url = "Enter where the button goes.";
  if (!form.cta_label.trim() && form.cta_url.trim()) fields.cta_label = "Enter the button text.";
  const cta = linkProblem(form.cta_url);
  if (cta) fields.cta_url = cta;
  const terms = linkProblem(form.terms_url);
  if (terms) fields.terms_url = terms;
  const words = [form.title, form.body, form.cta_label, form.terms];
  if (hasUrgency(...words)) fields.body = NO_URGENCY;
  if (
    mentionsMoney(form.title, form.body, form.cta_label) &&
    !form.terms.trim() &&
    !form.terms_url.trim()
  ) {
    fields.terms = TERMS_NEEDED;
  }
  if (form.priority === null || form.priority < 0 || form.priority > 1000) {
    fields.priority = "Use a whole number from 0 to 1000.";
  }
  const starts = startOf(form.starts);
  const ends = endOf(form.ends);
  let endsProblem = ends.problem;
  if (!endsProblem && starts.instant && ends.instant && ends.instant <= starts.instant) {
    endsProblem = { field: "date", message: "The end must be after the start." };
  }
  return { fields, starts: starts.problem, ends: endsProblem };
}

export const hasProblems = (p: OfferProblems) =>
  Object.keys(p.fields).length > 0 || p.starts !== null || p.ends !== null;

export function toCreate(form: OfferForm): OfferInput {
  return {
    title: form.title.trim(),
    body: orNull(form.body),
    image_media_id: form.image?.id ?? null,
    cta_label: orNull(form.cta_label),
    cta_url: orNull(form.cta_url),
    terms: orNull(form.terms),
    terms_url: orNull(form.terms_url),
    project_id: form.project_id || null,
    placement: form.placement,
    starts_at: startOf(form.starts).instant,
    ends_at: endOf(form.ends).instant,
    is_active: form.is_active,
    priority: form.priority ?? 0,
  };
}

export function toUpdate(form: OfferForm, saved: OfferForm): OfferUpdate {
  const next = toCreate(form);
  const before = toCreate(saved);
  const body: OfferUpdate = {};
  for (const key of Object.keys(next) as (keyof OfferInput)[]) {
    if (JSON.stringify(next[key]) !== JSON.stringify(before[key])) {
      (body as Record<string, unknown>)[key] = next[key];
    }
  }
  return body;
}

export const sameForm = (a: OfferForm, b: OfferForm) => Object.keys(toUpdate(a, b)).length === 0;
