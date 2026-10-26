"""Staff accounts → `User` responses: status, two-factor and when an invite was sent.

Collaborators: users/routes_admin.py, users/directory.py.
PERF: one extra query per page for the invite times, and the two-factor rows are loaded with the
users (selectinload), so a list never makes one query per row.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from empire_api.users.models import PasswordResetToken
from empire_api.users.models import User as UserRow
from empire_api.users.schemas import User


def _invite_times(db: Session, users: Sequence[UserRow]) -> dict[uuid.UUID, datetime]:
    invited = [u.id for u in users if u.password_hash is None]
    if not invited:
        return {}
    rows = db.execute(
        select(PasswordResetToken.user_id, func.max(PasswordResetToken.created_at))
        .where(PasswordResetToken.user_id.in_(invited), PasswordResetToken.purpose == "setup")
        .group_by(PasswordResetToken.user_id)
    ).all()
    return dict(rows)


def users_out(db: Session, users: Sequence[UserRow]) -> list[User]:
    times = _invite_times(db, users)
    out = []
    for user in users:
        item = User.model_validate(user)
        out.append(item.model_copy(update={"invite_sent_at": times.get(user.id)}))
    return out


def user_out(db: Session, user: UserRow) -> User:
    return users_out(db, [user])[0]
