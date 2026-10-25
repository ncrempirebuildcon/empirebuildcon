"""An offer's state on the website, and the light honesty checks on its wording.

Collaborators: offers.py (saving), schedule.py (the tick), present.py (`state` in responses).
Implements: ARCHITECTURE §9 (`offer.started` / `offer.ended`), AGENTS.md "No fake urgency".

State (computed, never stored), in this order:
  1. `ended`: the end time has passed (whether or not it is switched on).
  2. `inactive`: switched off (a draft, or taken down).
  3. `scheduled`: switched on, start time still ahead.
  4. `live`: switched on, started (or no start), not ended. Only `live` shows on the site.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Final

from empire_api.content.models import Offer
from empire_api.content.vocab import OfferState

# WHY a light check: an offer that mentions money (₹, Rs, lakh, crore, %, "discount", "off",
# "cashback", "free", "waiver", "save", "price") must say what it includes and its conditions,
# so it needs a terms line or a T&C link. A false positive only asks for terms, which an honest
# offer has anyway; a regex can't judge the wording, staff and the owner do.
_MONEY: Final = re.compile(
    r"₹|\brs\.?\s*\d|\binr\b|\d\s*%|\bper\s?cent\b|\blakhs?\b|\blacs?\b|\bcrores?\b|\bcr\b"
    r"|\bdiscount|\boff\b|\bcash\s?back\b|\bfree\b|\bwaiver|\bwaived\b|\bsave\b|\bsaving|\bprices?\b",
    re.IGNORECASE,
)
# COMPLIANCE (AGENTS.md "No fake urgency"; board NoirCmsContent: 'No countdown timers or "only
# N left" wording'): scarcity and pressure phrases are refused outright.
_URGENCY: Final = re.compile(
    r"\bonly\s+\d+\s+(?:units?\s+|homes?\s+|flats?\s+)?(?:left|remaining)\b|\bhurry\b"
    r"|\blast\s+(?:few|chance)\b|\bselling\s+fast\b|\bfew\s+(?:units?|homes?|flats?)\s+left\b"
    r"|\bbefore\s+it'?s\s+gone\b|\bcountdown\b",
    re.IGNORECASE,
)
TERMS_NEEDED: Final = (
    "This offer mentions a price or a discount, so add a terms line or a link to the terms "
    "and conditions (what it includes, who qualifies, until when)."
)
NO_URGENCY: Final = (
    'Remove pressure wording such as "only N left", "hurry" or "last few": offers state '
    "facts and their end date only."
)


def mentions_money(*texts: str | None) -> bool:
    return any(_MONEY.search(text or "") for text in texts)


def has_urgency(*texts: str | None) -> bool:
    return any(_URGENCY.search(text or "") for text in texts)


def is_live(offer: Offer, now: datetime) -> bool:
    return state_of(offer, now) == "live"


def state_of(offer: Offer, now: datetime) -> OfferState:
    """The module header's order. `now` is UTC-aware, like the stored times."""
    if offer.ends_at is not None and offer.ends_at <= now:
        return "ended"
    if not offer.is_active:
        return "inactive"
    if offer.starts_at is not None and offer.starts_at > now:
        return "scheduled"
    return "live"
