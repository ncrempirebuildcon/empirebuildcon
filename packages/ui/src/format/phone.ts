/**
 * Phone display helpers for the CMS: the masked number lists show ("+91 98xxxxxx10"), the full
 * number the lead detail shows ("+91 98765 43210"), and the tap-to-call and WhatsApp links.
 *
 * Numbers arrive from the API already normalised to E.164 (`+91XXXXXXXXXX`, ARCHITECTURE §8);
 * these helpers only format for display and never validate or normalise.
 *
 * COMPLIANCE: lists, cards and the dashboard show the masked form only; the full number appears
 * on the lead detail page, behind the same object-level check as the rest of the lead (DPDP Act,
 * SECURITY.md §8 "Access limited by role").
 */

const INDIA = "+91";

/** The national part of an Indian E.164 number ("9876543210"), or null for anything else. */
function indianNational(e164: string): string | null {
  if (!e164.startsWith(INDIA)) return null;
  const national = e164.slice(INDIA.length);
  return /^\d{10}$/.test(national) ? national : null;
}

/**
 * The masked number for lists: "+91 98xxxxxx10" (country code, first two and last two digits).
 *
 * WHY two and two: enough to tell two leads apart at a glance and to match a caller who reads
 * out the end of their number, without exposing the number to anyone looking over a shoulder.
 *
 * @param e164 The number as the API stores it, e.g. "+919876543210".
 * @returns The masked display string; a non-Indian number keeps its first four and last two
 *   characters. An erased lead's stub (no digits) is returned unchanged.
 */
export function maskPhone(e164: string): string {
  const national = indianNational(e164);
  if (national) return `${INDIA} ${national.slice(0, 2)}xxxxxx${national.slice(8)}`;
  if (!/^\+\d{8,15}$/.test(e164)) return e164;
  return `${e164.slice(0, 4)}${"x".repeat(e164.length - 6)}${e164.slice(-2)}`;
}

/**
 * The full number for the lead detail: "+91 98765 43210" (five and five, how numbers are read
 * out in India). Anything that isn't a 10-digit Indian number is shown as stored.
 */
export function formatPhone(e164: string): string {
  const national = indianNational(e164);
  if (!national) return e164;
  return `${INDIA} ${national.slice(0, 5)} ${national.slice(5)}`;
}

/** True for an Indian mobile number (starts 6–9), the only kind WhatsApp can reach. */
export function isIndianMobile(e164: string): boolean {
  const national = indianNational(e164);
  return national !== null && /^[6-9]/.test(national);
}

/** A tap-to-call link, `tel:+919876543210`, or null when the value holds no number (erased). */
export function telHref(e164: string): string | null {
  return /^\+\d{8,15}$/.test(e164) ? `tel:${e164}` : null;
}

/**
 * A WhatsApp click-to-chat link, `https://wa.me/919876543210` (digits only, no plus, as WhatsApp
 * asks), or null for a landline or an erased number.
 */
export function whatsappHref(e164: string): string | null {
  return isIndianMobile(e164) ? `https://wa.me/${e164.slice(1)}` : null;
}
