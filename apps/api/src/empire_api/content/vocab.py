"""The fixed word lists and limits of the content module, in one place: consent-text kinds (part
3), page kinds, block types, offer placements and states, and the draft marks (part 4).

Tables use the lists for CHECK constraints and the schemas use them as `Literal` types, so the
database, the API and the generated web client always agree (same pattern as projects/vocab.py).

`marketing` is an addition to the design contract's consent-kind enum (Phase 4 part 3): the
optional "news and offers" box is recorded separately from the required enquiry consent
(SECURITY.md §8).

DO NOT CHANGE a stored value without a migration: the CHECK constraints in
migrations/versions/0004_leads.py (consent kinds) and 0005_content.py (the rest) list them.
"""

from __future__ import annotations

from typing import Final, Literal, get_args

ConsentKind = Literal["lead_form", "marketing", "brochure", "cookies", "chat"]
CONSENT_KINDS: Final = get_args(ConsentKind)

# COMPLIANCE (D-017): Claude drafts the wording, the owner approves it. Until then a text says
# so in its own words, so nobody mistakes it for approved wording, and the dashboard lists it.
DRAFT_MARK: Final = "[DRAFT — awaiting owner approval]"
# COMPLIANCE (D-017): the placeholder the seed puts on every legal page. The real drafting comes
# in Phase 8 (o-20); production refuses to publish a legal page while its text says "[DRAFT".
LEGAL_DRAFT_MARK: Final = (
    "[DRAFT — text to be drafted by Claude and approved by the owner; see D-017]"
)

# --- Pages and blocks (ARCHITECTURE §6, design contract schemas Page and Block) ---------------

PageKind = Literal["standard", "landing", "legal", "system"]
PAGE_KINDS: Final = get_args(PageKind)
# Kinds staff may choose. System pages (home, about, contact, projects) come with the site from
# `empire-api seed`; they can't be created, deleted or renamed.
EditableKind = Literal["standard", "landing", "legal"]

BlockType = Literal[
    "hero",
    "rich_text",
    "image",
    "gallery",
    "video",
    "project_grid",
    "property_grid",
    "cta",
    "lead_form",
    "faq_list",
    "stats",
    "testimonials",
    "offer_banner",
    "map",
    "steps",
    "columns",
    "divider",
]
BLOCK_TYPES: Final = get_args(BlockType)
MAX_BLOCKS: Final = 60
MAX_GALLERY_IMAGES: Final = 24
MAX_GRID_CARDS: Final = 24
MAX_STEPS: Final = 8
MAX_STATS: Final = 6
MAX_PICKED: Final = 24  # chosen FAQ or testimonial ids in one block

# Forms a page block may show (leads/vocab.PublicSource minus chat and WhatsApp, which are not
# forms). Phase 5 renders them; Phase 5/6 submits them.
FormSource = Literal["contact_form", "project_form", "campaign", "site_visit", "brochure"]
VideoProvider = Literal["youtube", "vimeo"]

# --- Offers (ARCHITECTURE §9 offer.*) -----------------------------------------------------------

OfferPlacement = Literal["banner", "home", "project"]
OFFER_PLACEMENTS: Final = get_args(OfferPlacement)
# Computed, never stored (offers.state_of): what the website shows right now.
OfferState = Literal["scheduled", "live", "ended", "inactive"]

# --- Posts ------------------------------------------------------------------------------------

MAX_TAGS: Final = 10
