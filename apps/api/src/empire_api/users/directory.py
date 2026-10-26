"""Read-only service functions other modules call about staff accounts: display names for
`UserRef`s, and who currently holds a permission (e.g. who can own a lead).

Collaborators: leads (owners, note authors, activity actors), content (consent-text authors),
dashboard. Implements: ARCHITECTURE §2 (modules call service functions, not other modules'
tables), §11 (the permission matrix in users/roles.py decides "holds").
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.users.models import User
from empire_api.users.roles import ROLE_KEYS, has_permission
from empire_api.users.schemas import UserRef

# WHY: a UserRef must always carry a name, but accounts are deactivated, never deleted; this only
# shows if a row was removed by hand in the database.
UNKNOWN_NAME: Final = "Former staff member"


def user_refs(db: Session, user_ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, UserRef]:
    """user id → UserRef (id and name) for every id given (None ignored)."""
    ids = {user_id for user_id in user_ids if user_id is not None}
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.name).where(User.id.in_(ids))).all()
    found = {user_id: UserRef(id=user_id, name=name) for user_id, name in rows}
    return {user_id: found.get(user_id, UserRef(id=user_id, name=UNKNOWN_NAME)) for user_id in ids}


def roles_with(permission: str) -> list[str]:
    return [role for role in ROLE_KEYS if has_permission(role, permission)]


def active_users_with(db: Session, permission: str) -> list[User]:
    """Active accounts whose role holds `permission`, by name."""
    return list(
        db.scalars(
            select(User)
            .where(User.is_active.is_(True), User.role.in_(roles_with(permission)))
            .order_by(User.name, User.id)
        )
    )


def is_active_with(db: Session, user_id: uuid.UUID, permission: str) -> bool:
    """Whether this account exists, is active, and its role holds `permission`."""
    user = db.get(User, user_id)
    return bool(user and user.is_active and has_permission(user.role, permission))


def active_users_in_role(db: Session, role: str) -> list[uuid.UUID]:
    """Active accounts of one role, oldest first (the default round-robin order)."""
    return list(
        db.scalars(
            select(User.id)
            .where(User.is_active.is_(True), User.role == role)
            .order_by(User.created_at, User.id)
        )
    )
