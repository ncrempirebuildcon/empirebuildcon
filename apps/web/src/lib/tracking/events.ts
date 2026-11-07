/**
 * The browser event a lead form fires after the API accepted an enquiry (task 6.3, D-058).
 * Only the reference travels: never the name, phone or anything typed. The tag loader listens
 * for it, and only tags the visitor allowed hear about it.
 */
export const LEAD_EVENT_NAME = "empire:lead";

export interface LeadEventDetail {
  reference: string;
}

export function announceLead(reference: string): void {
  try {
    window.dispatchEvent(
      new CustomEvent<LeadEventDetail>(LEAD_EVENT_NAME, { detail: { reference } }),
    );
  } catch {
    // A tracking problem must never break the form.
  }
}
