"""Request and response shapes for consent texts (design contract schemas ConsentText and
ConsentTextInput).

Additions to the contract (Phase 4 part 3): `marketing` in the kind enum; on ConsentText,
`created_at`, `created_by` and `is_draft` (the wording still carries the draft mark, D-017).

SECURITY (SECURITY.md §5): the input rejects unknown fields and every string is bounded.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from empire_api.content.vocab import ConsentKind
from empire_api.projects.fields import Line300, OutModel, StrictModel, Text5000
from empire_api.users.schemas import UserRef


class ConsentText(OutModel):
    id: uuid.UUID
    kind: ConsentKind
    version: int
    body: str
    checkbox_label: str
    published_at: datetime | None
    is_current: bool
    is_draft: bool = Field(
        description="The wording still says it awaits the owner's approval (D-017). Production "
        "refuses to publish such a text."
    )
    created_at: datetime
    created_by: UserRef | None


class ConsentTextInput(StrictModel):
    """A new draft version. Published texts are never edited: send a new version instead."""

    kind: ConsentKind
    body: Text5000
    checkbox_label: Line300
