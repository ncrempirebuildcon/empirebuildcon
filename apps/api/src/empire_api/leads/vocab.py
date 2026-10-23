"""The fixed word lists and limits of the leads module (design contract enums), in one place.

Tables use the lists for CHECK constraints and the schemas use them as `Literal` types, so the
database, the API and the generated web client always agree (same pattern as projects/vocab.py).

DO NOT CHANGE a stored value without a migration: rows already hold these strings, and the CHECK
constraints in migrations/versions/0004_leads.py list them.
"""

from __future__ import annotations

from typing import Final, Literal, get_args

LeadStatus = Literal["new", "contacted", "site_visit", "negotiation", "booked", "lost"]
LeadSource = Literal[
    "project_form",
    "contact_form",
    "brochure",
    "site_visit",
    "campaign",
    "chat",
    "whatsapp",
    "phone",
    "manual",
]
# Sources a visitor's browser may claim. `phone` and `manual` are entered by staff only.
PublicSource = Literal[
    "project_form", "contact_form", "brochure", "site_visit", "campaign", "chat", "whatsapp"
]
Language = Literal["en", "hi"]
LeadConsentKind = Literal["lead_form", "marketing"]
# Contract enum plus additions (recorded in the part 3 report): `unread`, `details_changed`,
# `spam_marked`, `duplicate_linked` and `erased`.
ActivityKind = Literal[
    "created",
    "status_changed",
    "assigned",
    "note_added",
    "visit_requested",
    "visit_updated",
    "alert_sent",
    "webhook_sent",
    "exported",
    "read",
    "unread",
    "details_changed",
    "spam_marked",
    "duplicate_linked",
    "erased",
]
# Why a lead was lost: a fixed list (the CMS's dropdown), so reports can count it and erasure has
# no free text to hunt for. Anything else is `other` with a short note (`lost_reason_note`).
LostReason = Literal[
    "bought_elsewhere",
    "budget",
    "location",
    "not_reachable",
    "not_looking",
    "duplicate",
    "other",
]
VisitStatus = Literal["requested", "confirmed", "completed", "no_show", "cancelled"]
VisitSlot = Literal["morning", "afternoon", "evening"]
UtmGroup = Literal["source", "medium", "campaign", "project"]
# DELETE /admin/leads/{id}: the lead's duplicate group, or every lead with the same phone.
ErasureScope = Literal["group", "person"]

LEAD_STATUSES: Final = get_args(LeadStatus)
LEAD_SOURCES: Final = get_args(LeadSource)
LANGUAGES: Final = get_args(Language)
LEAD_CONSENT_KINDS: Final = get_args(LeadConsentKind)
ACTIVITY_KINDS: Final = get_args(ActivityKind)
VISIT_STATUSES: Final = get_args(VisitStatus)
LOST_REASONS: Final = get_args(LostReason)
# The CMS's wording for each code (the leads board's "Reason" dropdown).
LOST_REASON_LABELS: Final[dict[str, str]] = {
    "bought_elsewhere": "Bought elsewhere",
    "budget": "Budget doesn't fit",
    "location": "Location doesn't suit",
    "not_reachable": "Not reachable after 3 tries",
    "not_looking": "No longer looking",
    "duplicate": "Duplicate lead",
    "other": "Other",
}
VISIT_SLOTS: Final = get_args(VisitSlot)

# The pipeline in order (ARCHITECTURE §8). `booked` and `lost` are both ends; moving to an
# earlier stage is allowed (staff correct mistakes) and recorded as "backward".
PIPELINE: Final[dict[str, int]] = {
    "new": 0,
    "contacted": 1,
    "site_visit": 2,
    "negotiation": 3,
    "booked": 4,
    "lost": 4,
}
# A visit still on the calendar (counts as "visits today / this week", upcoming list).
OPEN_VISIT_STATUSES: Final = ("requested", "confirmed")
# A lead still being worked: not finished (and not erased). The inbox's `open=true`.
CLOSED_STATUSES: Final = ("booked", "lost")

# What erasure and retention leave in place of a person's details (ARCHITECTURE §6).
ERASED: Final = "[erased]"

# Duplicate check (ARCHITECTURE §8): same phone and project within this many hours.
DUPLICATE_WINDOW_HOURS: Final = 24
# Public intake rate limits (ARCHITECTURE §8): per IP hash and per phone, in PostgreSQL.
INTAKE_LIMIT: Final = 5
INTAKE_WINDOW_SECONDS: Final = 600
# A visitor may ask for a visit from today up to this many days ahead (IST).
VISIT_MAX_DAYS_AHEAD: Final = 120
# CSV export cap: an export above it is refused with a "narrow the filters" message, never cut
# off silently.
EXPORT_MAX_ROWS: Final = 50_000
# Calendar list cap (PERF: a week or a month of visits is a few dozen rows).
VISITS_MAX_ROWS: Final = 500
