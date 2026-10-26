/**
 * Words the lead screens show for the API's enum values, in the CMS boards' wording
 * (NoirCmsLeads, NoirCmsLead, NoirCmsVisits): pipeline stages, sources, site-visit states and
 * time slots, lost reasons and activity titles.
 *
 * Keys are typed from the generated client, so a new or renamed value fails the type-check here
 * instead of showing a raw key on screen.
 */
import type { ChipVariant } from "@empire/ui";
import type { Schema } from "../api";

export type Lead = Schema<"Lead">;
export type LeadStatus = Lead["status"];
export type LeadSource = Lead["source"];
export type SiteVisit = Schema<"SiteVisit">;
export type VisitStatus = SiteVisit["status"];
export type ActivityKind = Schema<"LeadActivity">["kind"];

/** The pipeline in order (ARCHITECTURE §8): new → contacted → site_visit → negotiation → booked / lost. */
export const LEAD_STATUS_ORDER: readonly LeadStatus[] = [
  "new",
  "contacted",
  "site_visit",
  "negotiation",
  "booked",
  "lost",
];

export const LEAD_STATUS: Record<LeadStatus, string> = {
  new: "New",
  contacted: "Contacted",
  site_visit: "Site visit",
  negotiation: "Negotiation",
  booked: "Booked",
  lost: "Lost",
};

export const LEAD_STATUS_CHIP: Record<LeadStatus, ChipVariant> = {
  new: "stageNew",
  contacted: "stageContacted",
  site_visit: "stageSiteVisit",
  negotiation: "stageNegotiation",
  booked: "stageBooked",
  lost: "stageLost",
};

/** Where the lead came from, in the boards' words ("Project form", "Contact page", …). */
export const LEAD_SOURCE: Record<LeadSource, string> = {
  project_form: "Project form",
  contact_form: "Contact page",
  brochure: "Brochure",
  site_visit: "Site-visit form",
  campaign: "Campaign landing",
  chat: "Chat",
  whatsapp: "WhatsApp",
  phone: "Phone call",
  manual: "Walk-in or other",
};

/** Sources staff can pick for a lead they add by hand (walk-ins and calls come in person). */
export const MANUAL_SOURCES: readonly LeadSource[] = ["phone", "whatsapp", "manual"];

/** Why a lead was lost: a fixed code (`Lead.lost_reason`), so reports can count it. */
export type LostReason = NonNullable<Lead["lost_reason"]>;

/**
 * The reasons offered when a lead is marked lost, in the board's words (NoirCmsLead). "Other"
 * needs a few words of its own (`lost_reason_note`, up to 200 characters); the API refuses
 * "other" without them.
 */
export const LOST_REASON: Record<LostReason, string> = {
  bought_elsewhere: "Bought elsewhere",
  budget: "Budget doesn't fit",
  location: "Location doesn't suit",
  not_reachable: "Not reachable after 3 tries",
  not_looking: "No longer looking",
  duplicate: "Duplicate lead",
  other: "Other reason",
};

/** "Bought elsewhere", or for "other" the staff's own words; null when there is no reason. */
export function lostReasonLabel(
  lead: Pick<Lead, "lost_reason" | "lost_reason_note">,
): string | null {
  if (!lead.lost_reason) return null;
  if (lead.lost_reason === "other") return lead.lost_reason_note || LOST_REASON.other;
  return lead.lost_reason_note
    ? `${LOST_REASON[lead.lost_reason]} (${lead.lost_reason_note})`
    : LOST_REASON[lead.lost_reason];
}

export const VISIT_STATUS: Record<VisitStatus, string> = {
  requested: "Requested · to confirm",
  confirmed: "Confirmed",
  completed: "Done",
  no_show: "No-show",
  cancelled: "Cancelled",
};

/** Short state names for filters ("Requested" rather than "Requested · to confirm"). */
export const VISIT_STATUS_SHORT: Record<VisitStatus, string> = {
  requested: "Requested",
  confirmed: "Confirmed",
  completed: "Done",
  no_show: "No-show",
  cancelled: "Cancelled",
};

// WHY existing chip styles: the visits board draws "Requested" with the gold outline and
// "Confirmed" with the palm outline; done, no-show and cancelled follow the booked, sold-out and
// archived chips, so the CMS keeps one small set of chip looks.
export const VISIT_STATUS_CHIP: Record<VisitStatus, ChipVariant> = {
  requested: "scheduled",
  confirmed: "published",
  completed: "stageBooked",
  no_show: "soldOut",
  cancelled: "archived",
};

/** The time of day a buyer asks for (D-016: sales confirms the exact time by phone). */
export const VISIT_SLOTS = ["morning", "afternoon", "evening"] as const;
export type VisitSlot = (typeof VISIT_SLOTS)[number];

export const VISIT_SLOT: Record<VisitSlot, string> = {
  morning: "Morning",
  afternoon: "Afternoon",
  evening: "Evening",
};

/** The slot's label, or the raw value if the API sends one this screen doesn't know yet. */
export function slotLabel(slot: string | null | undefined): string {
  if (!slot) return "Any time";
  return Object.hasOwn(VISIT_SLOT, slot) ? VISIT_SLOT[slot as VisitSlot] : slot;
}

export const ACTIVITY_TITLE: Record<ActivityKind, string> = {
  created: "Lead created",
  status_changed: "Stage changed",
  assigned: "Owner changed",
  note_added: "Note added",
  visit_requested: "Site visit requested",
  visit_updated: "Site visit updated",
  alert_sent: "Alert sent",
  webhook_sent: "Sent to a connected system",
  exported: "Included in a CSV export",
  read: "Marked read",
  unread: "Marked unread",
  details_changed: "Details changed",
  spam_marked: "Spam flag changed",
  duplicate_linked: "Repeat enquiry linked",
  erased: "Personal data erased",
};
