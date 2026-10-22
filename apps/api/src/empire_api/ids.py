"""Primary-key helpers.

WHY: UUID v7 is time-ordered, so new rows land at the end of the B-tree index (fast inserts,
natural "newest last" order) while staying unguessable enough for URLs (ARCHITECTURE §6).
"""

from __future__ import annotations

import uuid

import uuid_utils.compat as uuid_compat


def new_id() -> uuid.UUID:
    """A new UUID v7 as a standard-library `uuid.UUID` (what SQLAlchemy and Pydantic expect)."""
    value: uuid.UUID = uuid_compat.uuid7()
    return value
