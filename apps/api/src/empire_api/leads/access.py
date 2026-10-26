"""Who may see which lead: the object-level rule of SECURITY.md §1, in one place.

Collaborators: every staff read and write in service.py, visits.py, export.py, report.py and
dashboard/service.py goes through `scope_leads` / `load_lead`.
Implements: SECURITY.md §1–2 ("sales users without leads.read_all only see their own leads, in
lists, detail, exports and reports"), ARCHITECTURE §11.

SECURITY: without `leads.read_all`, a staff member sees only the leads they own: in the inbox,
detail, notes, activity, visits, the export, the dashboard and the UTM report. A lead they may
not see answers 404, exactly like a lead that doesn't exist, so lead ids can't be probed.
SECURITY: the UTM report is counts only. Roles that hold `leads.report` but not `leads.read`
(marketing) see the counts for every lead: that is why the matrix gives them the report, and
no personal data is in it. Sales (leads.read without leads.read_all) see counts for their own
leads only, like everywhere else.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Final

from fastapi import Request
from sqlalchemy import Select
from sqlalchemy.orm import Session

from empire_api.errors import ApiProblem
from empire_api.leads.models import Lead
from empire_api.platform.crypto import client_ip
from empire_api.projects.common import Actor
from empire_api.users.roles import has_permission
from empire_api.users.sessions import SessionInfo

NO_LEAD: Final = "No lead with this id."


@dataclass(frozen=True)
class Staff:
    """The signed-in staff member as the leads services need them."""

    user_id: uuid.UUID
    role: str
    ip: str | None = None

    @classmethod
    def of(cls, info: SessionInfo, request: Request | None = None) -> Staff:
        return cls(
            user_id=info.user.id,
            role=info.user.role,
            ip=client_ip(request) if request is not None else None,
        )

    def can(self, permission: str) -> bool:
        return has_permission(self.role, permission)

    @property
    def sees_all_leads(self) -> bool:
        return self.can("leads.read_all")

    @property
    def actor(self) -> Actor:
        """For the shared audit helpers (platform/audit.py through projects/common.py)."""
        return Actor(user_id=self.user_id, ip=self.ip)


def owner_filter(staff: Staff) -> uuid.UUID | None:
    """The owner every lead query must be limited to, or None when the staff member sees all.

    SECURITY: the one place that decides; callers add `Lead.owner_user_id == <this>`.
    """
    return None if staff.sees_all_leads else staff.user_id


def report_owner_filter(staff: Staff) -> uuid.UUID | None:
    """The UTM report's scope (module header): own leads for sales, all for everyone else."""
    if staff.sees_all_leads or not staff.can("leads.read"):
        return None
    return staff.user_id


def scope_leads[S: Select[*tuple[Any, ...]]](stmt: S, staff: Staff) -> S:
    """Limit a query that selects from `lead` to the leads this staff member may see."""
    owner = owner_filter(staff)
    return stmt if owner is None else stmt.where(Lead.owner_user_id == owner)


def can_see(lead: Lead, staff: Staff) -> bool:
    owner = owner_filter(staff)
    return owner is None or lead.owner_user_id == owner


def load_lead(db: Session, lead_id: uuid.UUID, staff: Staff, *, lock: bool = False) -> Lead:
    """The lead, or 404 when it doesn't exist OR this staff member may not see it.

    `lock=True` holds the row until commit (FOR UPDATE), for every write.
    """
    lead = db.get(Lead, lead_id, with_for_update=lock, populate_existing=True)
    if lead is None or not can_see(lead, staff):
        raise ApiProblem(404, NO_LEAD)
    return lead
