"""Read-only service functions other modules call about staff accounts: display names for
`UserRef`s, and who currently holds a permission (e.g. who can own a lead).

Collaborators: leads (owners, note authors, activity actors), content (consent-text authors),
dashboard, mail (who an email goes to), site_settings (lead routing checks).
Implements: ARCHITECTURE §2 (modules call service functions, not other modules' tables), §11
(the permission matrix in users/roles.py decides "holds").
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
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


def ready_users_with(db: Session, permission: str) -> list[User]:
    """Accounts that can sign in (active AND their own password set: not just invited) and
    whose role holds `permission`, by name."""
    return list(
        db.scalars(
            select(User)
            .where(
                User.is_active.is_(True),
                User.password_hash.is_not(None),
                User.role.in_(roles_with(permission)),
            )
            .order_by(User.name, User.id)
        )
    )


@dataclass(frozen=True)
class Standing:
    """What another module may know about an account to decide whether it can be given work."""

    role: str
    is_active: bool
    has_password: bool


def standing(db: Session, user_id: uuid.UUID) -> Standing | None:
    user = db.get(User, user_id)
    if user is None:
        return None
    return Standing(
        role=user.role, is_active=user.is_active, has_password=user.password_hash is not None
    )


def is_active_with(db: Session, user_id: uuid.UUID, permission: str) -> bool:
    """Whether this account exists, is active, and its role holds `permission`."""
    user = db.get(User, user_id)
    return bool(user and user.is_active and has_permission(user.role, permission))


def ready_users_in_role(db: Session, role: str) -> list[uuid.UUID]:
    """Accounts of one role that can sign in (active, own password set), oldest first (the
    default round-robin order)."""
    return list(
        db.scalars(
            select(User.id)
            .where(User.is_active.is_(True), User.password_hash.is_not(None), User.role == role)
            .order_by(User.created_at, User.id)
        )
    )


@dataclass(frozen=True)
class Recipient:
    """Who an email goes to (mail/handlers.py). Only active accounts are ever recipients."""

    user_id: uuid.UUID
    email: str
    name: str


def active_account(db: Session, user_id: uuid.UUID | None) -> Recipient | None:
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        return None
    return Recipient(user_id=user.id, email=user.email, name=user.name)


def active_super_admins(db: Session) -> list[Recipient]:
    """Every active super-admin: the lead alert's fallback when no sales inbox is set."""
    rows = db.scalars(
        select(User)
        .where(User.is_active.is_(True), User.role == "super_admin")
        .order_by(User.created_at, User.id)
    )
    return [Recipient(user_id=u.id, email=u.email, name=u.name) for u in rows]


def names_and_roles(
    db: Session, user_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, str, bool]]:
    """user id → (name, role, is_active), for the Settings round-robin table."""
    ids = set(user_ids)
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.name, User.role, User.is_active).where(User.id.in_(ids)))
    return {user_id: (name, role, active) for user_id, name, role, active in rows}
