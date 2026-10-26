/**
 * One line of detail for each entry in a lead's activity timeline (board NoirCmsLead
 * "Activity"), from the entry's `data`.
 *
 * The API keeps `data` to ids, stages, dates and times (never personal data, leads/effects.py),
 * so this file turns those into words: "Contacted → Site visit", "Sat 24 Oct · morning",
 * "Owner: Sales 1". Anything it doesn't recognise is left out rather than shown raw.
 */
import { formatCalendarDate, formatVisitTime } from "../dates";
import {
  LEAD_SOURCE,
  LEAD_STATUS,
  LOST_REASON,
  VISIT_STATUS,
  lostReasonLabel,
  slotLabel,
  type LeadSource,
  type LostReason,
} from "./labels";
import type { Schema } from "../api";

type Activity = Schema<"LeadActivity">;

const text = (value: unknown): string | null =>
  typeof value === "string" && value.trim() ? value : null;

function stage(value: unknown): string | null {
  const key = text(value);
  return key && Object.hasOwn(LEAD_STATUS, key)
    ? LEAD_STATUS[key as keyof typeof LEAD_STATUS]
    : null;
}

function visitStatus(value: unknown): string | null {
  const key = text(value);
  return key && Object.hasOwn(VISIT_STATUS, key)
    ? VISIT_STATUS[key as keyof typeof VISIT_STATUS]
    : null;
}

function isoDate(value: unknown): string | null {
  const day = text(value);
  return day && /^\d{4}-\d{2}-\d{2}$/.test(day) ? formatCalendarDate(day) : null;
}

function instant(value: unknown): string | null {
  const iso = text(value);
  return iso && !Number.isNaN(Date.parse(iso)) ? formatVisitTime(iso) : null;
}

/**
 * The detail line for an activity entry, or null when there is nothing worth adding.
 * `nameOf` turns a staff id into a name (from the lead-owners list), when known.
 */
export function describeActivity(
  entry: Activity,
  nameOf: (userId: string) => string | null,
): string | null {
  const data = (entry.data ?? {}) as Record<string, unknown>;
  switch (entry.kind) {
    case "status_changed": {
      const from = stage(data.from);
      const to = stage(data.to);
      const code = text(data.lost_reason);
      const note = text(data.lost_reason_note);
      const reason =
        code && Object.hasOwn(LOST_REASON, code)
          ? lostReasonLabel({ lost_reason: code as LostReason, lost_reason_note: note })
          : note;
      const parts = [
        from && to ? `${from} → ${to}` : to,
        data.direction === "backward" ? "moved back" : null,
        data.via === "site_visit_confirmed" ? "when the site visit was confirmed" : null,
        reason ? `reason: ${reason}` : null,
      ];
      return parts.filter(Boolean).join(" · ") || null;
    }
    case "assigned": {
      const to = text(data.to_user_id);
      return to ? `To ${nameOf(to) ?? "another staff member"}` : "To the sales inbox (unassigned)";
    }
    case "created": {
      const source = text(data.source);
      const intent = text(data.intent);
      const how: Record<string, string> = {
        enquiry: "Enquiry form",
        site_visit: "Site-visit request",
        brochure: "Brochure request",
        manual: "Added by staff",
        sample: "Sample data",
      };
      const parts = [
        intent && how[intent] ? how[intent] : null,
        source && Object.hasOwn(LEAD_SOURCE, source) ? LEAD_SOURCE[source as LeadSource] : null,
        "consent recorded",
      ];
      return parts.filter(Boolean).join(" · ");
    }
    case "visit_requested": {
      const day = isoDate(data.preferred_date);
      const slot = text(data.preferred_slot);
      return day ? `${day}${slot ? ` · ${slotLabel(slot).toLowerCase()}` : ""}` : null;
    }
    case "visit_updated": {
      const from = visitStatus(data.from_status);
      const to = visitStatus(data.to_status);
      const when = instant(data.confirmed_for);
      const parts = [
        from && to && from !== to ? `${from} → ${to}` : to,
        when ? `${when} IST` : null,
      ];
      return parts.filter(Boolean).join(" · ") || null;
    }
    case "spam_marked":
      return data.is_spam === false ? "No longer spam" : "Marked as spam";
    case "duplicate_linked": {
      // A link to a lead this viewer may not open arrives as a summary only (no reference).
      const summary = text(data.summary);
      if (summary) return summary;
      const reference = text(data.reference);
      return `A repeat enquiry (same mobile and project within 24 hours)${reference ? `: ${reference}` : ""}`;
    }
    case "details_changed": {
      const fields = Array.isArray(data.fields)
        ? data.fields.filter((field): field is string => typeof field === "string")
        : [];
      const words: Record<string, string> = {
        email: "email",
        preferred_bhk: "interest",
        budget_max_inr: "budget",
        project_id: "project",
        configuration_id: "configuration",
        lost_reason: "lost reason",
        lost_reason_note: "lost reason in words",
      };
      return fields.length
        ? `Changed: ${fields.map((field) => words[field] ?? field.replace(/_/g, " ")).join(", ")}`
        : null;
    }
    case "exported": {
      const rows = typeof data.rows === "number" ? data.rows : null;
      return rows
        ? `A CSV of ${rows.toLocaleString("en-IN")} ${rows === 1 ? "lead" : "leads"}`
        : null;
    }
    case "erased":
      return data.reason === "retention"
        ? "Retention rule (no activity for the set period): personal details replaced with a stub"
        : "On the person's request: personal details replaced with a stub";
    default:
      return null;
  }
}
