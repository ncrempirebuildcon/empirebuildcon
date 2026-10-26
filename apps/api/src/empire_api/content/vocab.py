"""The fixed word lists of the content module. Part 3: the kinds of consent text.

`marketing` is an addition to the design contract's enum (Phase 4 part 3): the optional
"news and offers" box is recorded separately from the required enquiry consent (SECURITY.md §8).

DO NOT CHANGE a stored value without a migration: the CHECK constraint in
migrations/versions/0004_leads.py lists them.
"""

from __future__ import annotations

from typing import Final, Literal, get_args

ConsentKind = Literal["lead_form", "marketing", "brochure", "cookies", "chat"]
CONSENT_KINDS: Final = get_args(ConsentKind)

# COMPLIANCE (D-017): Claude drafts the wording, the owner approves it. Until then a text says
# so in its own words, so nobody mistakes it for approved wording, and the dashboard lists it.
DRAFT_MARK: Final = "[DRAFT — awaiting owner approval]"
