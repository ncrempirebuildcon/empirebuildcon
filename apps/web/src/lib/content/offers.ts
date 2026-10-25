/**
 * The light honesty checks on an offer's wording, the same as the API's (offers_state.py), so
 * staff see them next to the field before saving. The API is the guard and checks again.
 *
 * COMPLIANCE (AGENTS.md "No fake urgency"; board NoirCmsContent): no countdowns, no "only N
 * left" or "hurry"; an offer that mentions money must say what it includes and until when (a
 * terms line or a T&C link).
 * WHY a light check: a word list can't judge wording; a false alarm only asks for terms, which
 * an honest offer has anyway. Staff and the owner judge the rest.
 */

const MONEY =
  /₹|\brs\.?\s*\d|\binr\b|\d\s*%|\bper\s?cent\b|\blakhs?\b|\blacs?\b|\bcrores?\b|\bcr\b|\bdiscount|\boff\b|\bcash\s?back\b|\bfree\b|\bwaiver|\bwaived\b|\bsave\b|\bsaving|\bprices?\b/i;

const URGENCY =
  /\bonly\s+\d+\s+(?:units?\s+|homes?\s+|flats?\s+)?(?:left|remaining)\b|\bhurry\b|\blast\s+(?:few|chance)\b|\bselling\s+fast\b|\bfew\s+(?:units?|homes?|flats?)\s+left\b|\bbefore\s+it'?s\s+gone\b|\bcountdown\b/i;

export const TERMS_NEEDED =
  "This offer mentions a price or a discount, so add a terms line or a link to the terms and conditions (what it includes, who qualifies, until when).";

export const NO_URGENCY =
  'Remove pressure wording such as "only N left", "hurry" or "last few": offers state facts and their end date only.';

/** True when any text mentions money (₹, lakh, %, discount, free, price…). */
export const mentionsMoney = (...texts: (string | null | undefined)[]) =>
  texts.some((text) => MONEY.test(text ?? ""));

/** True when any text uses pressure wording. */
export const hasUrgency = (...texts: (string | null | undefined)[]) =>
  texts.some((text) => URGENCY.test(text ?? ""));
