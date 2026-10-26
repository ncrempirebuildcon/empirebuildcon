"""Reading the audit log for the CMS (GET /admin/audit-log): filters, actor names and roles, and
IP addresses masked further for display.

Collaborators: users/routes_admin.py (HTTP), platform/models.AuditLog (the table),
platform/audit.py (the writer, which already stores only a masked network).
Implements: ARCHITECTURE §11 (who, what, before/after, IP), SECURITY.md §11.

INVARIANT: read only. Nothing here updates or deletes an audit row (platform/models.AuditLog).
SECURITY: the stored network (/24 for IPv4, /48 for IPv6) is shown even coarser: the first two
parts of an IPv4 address ("49.36.xxx.xxx") or the /32 of an IPv6 address. That is enough to
see "same place as usual" or "somewhere new", without showing staff where a colleague lives.
"""

from __future__ import annotations

import ipaddress
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from empire_api.pagination import PageParams
from empire_api.platform.models import AuditLog
from empire_api.timeutil import IST
from empire_api.users.models import User
from empire_api.users.schemas import AuditActor, AuditEntry, AuditList, PageMeta


@dataclass(frozen=True)
class AuditFilters:
    actor_id: uuid.UUID | None = None
    system: bool = False
    entity_type: str | None = None
    entity_id: str | None = None
    action: str | None = None
    action_prefix: str | None = None
    date_from: date | None = None
    date_to: date | None = None


def ist_start(day: date) -> datetime:
    """Midnight at the start of an IST day (stored times are UTC; staff think in IST)."""
    return datetime.combine(day, time.min, tzinfo=IST)


def _like_prefix(prefix: str) -> str:
    return prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _query(filters: AuditFilters) -> Select[AuditLog]:
    stmt = select(AuditLog)
    if filters.actor_id:
        stmt = stmt.where(AuditLog.actor_user_id == filters.actor_id)
    if filters.system:
        stmt = stmt.where(AuditLog.actor_user_id.is_(None))
    if filters.entity_type:
        stmt = stmt.where(AuditLog.entity_type == filters.entity_type)
    if filters.entity_id:
        stmt = stmt.where(AuditLog.entity_id == filters.entity_id)
    if filters.action:
        stmt = stmt.where(AuditLog.action == filters.action)
    if filters.action_prefix:
        stmt = stmt.where(AuditLog.action.like(_like_prefix(filters.action_prefix), escape="\\"))
    if filters.date_from:
        stmt = stmt.where(AuditLog.created_at >= ist_start(filters.date_from))
    if filters.date_to:
        stmt = stmt.where(AuditLog.created_at < ist_start(filters.date_to + timedelta(days=1)))
    return stmt


def display_ip(stored: str | None) -> str | None:
    """'49.36.12.0/24' → '49.36.xxx.xxx'; '2001:db8:1::/48' → '2001:db8::/32' (module header)."""
    if not stored:
        return None
    try:
        network = ipaddress.ip_network(stored, strict=False)
    except ValueError:
        return None
    if network.version == 4:
        first, second = str(network.network_address).split(".")[:2]
        return f"{first}.{second}.xxx.xxx"
    wide = network.supernet(new_prefix=32) if network.prefixlen > 32 else network
    return str(wide)


def _actors(db: Session, rows: list[AuditLog]) -> dict[uuid.UUID, AuditActor]:
    ids = {r.actor_user_id for r in rows if r.actor_user_id}
    if not ids:
        return {}
    found = {
        user_id: AuditActor(id=user_id, name=name, role=role)
        for user_id, name, role in db.execute(
            select(User.id, User.name, User.role).where(User.id.in_(ids))
        )
    }
    return {
        user_id: found.get(user_id, AuditActor(id=user_id, name="Former user", role=None))
        for user_id in ids
    }


def audit_page(db: Session, filters: AuditFilters, paging: PageParams) -> AuditList:
    """One page of entries, newest first, with the total for the pager."""
    stmt = _query(filters)
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list(
        db.scalars(
            stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset(paging.offset)
            .limit(paging.per_page)
        )
    )
    actors = _actors(db, rows)
    items = [
        AuditEntry(
            id=r.id,
            actor=actors.get(r.actor_user_id) if r.actor_user_id else None,
            action=r.action,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            changes=r.changes,
            ip=display_ip(r.ip),
            created_at=r.created_at,
        )
        for r in rows
    ]
    return AuditList(items=items, meta=PageMeta(**paging.meta(total)))
