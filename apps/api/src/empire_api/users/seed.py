"""SAMPLE staff accounts for `empire-api seed --sample` (development and test only, D-015).

They exist so the users-and-roles screen has rows to show in screenshots and demos.

COMPLIANCE / SECURITY:
  - Refused unless APP_ENV is development or test (never staging or production).
  - Named "Sample …", on example.com (reserved by RFC 2606, never receives mail).
  - No password and no setup link: they stay "invited" and can never sign in. No email is
    queued for them, and nothing personal is stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.users.models import User
from empire_api.users.service import find_user_by_email

SAMPLE_USERS: Final = (
    ("Sample Sales 1", "sample.sales1@example.com", "sales"),
    ("Sample Sales 2", "sample.sales2@example.com", "sales"),
    ("Sample Marketing 1", "sample.marketing1@example.com", "marketing"),
    ("Sample Editor 1", "sample.editor1@example.com", "content_editor"),
)


class SampleUsersRefusedError(RuntimeError):
    """Sample accounts outside development and test."""


@dataclass(frozen=True)
class SampleUsersResult:
    added: int
    skipped: int


def seed_sample_users(db: Session) -> SampleUsersResult:
    """Add the missing sample accounts. Caller commits."""
    if get_settings().app_env not in ("development", "test"):
        raise SampleUsersRefusedError("Sample accounts are added only in development and test.")
    added = skipped = 0
    for name, email, role in SAMPLE_USERS:
        if find_user_by_email(db, email) is not None:
            skipped += 1
            continue
        db.add(User(email=email, name=name, role=role, is_active=True, password_hash=None))
        added += 1
    db.flush()
    return SampleUsersResult(added=added, skipped=skipped)
