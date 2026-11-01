"""Shared search database helpers.

COMPLIANCE: PgBouncer transaction-mode safe search configuration helpers (D-038).
Admin and public search endpoints use this module.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def set_search_trgm_threshold(db: Session, threshold: str = "0.5") -> None:
    """Set pg_trgm.word_similarity_threshold transaction-locally (D-038).

    COMPLIANCE: Uses is_local=true so this setting applies only to the current transaction.
    This works reliably across connection poolers (e.g. PgBouncer on Neon in transaction mode)
    without depending on session persistence or startup parameters.
    """
    db.execute(
        text("SELECT set_config('pg_trgm.word_similarity_threshold', :val, true)"),
        {"val": threshold},
    )
