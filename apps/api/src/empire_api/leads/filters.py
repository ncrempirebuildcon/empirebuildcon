"""The inbox filters, turned into SQL conditions once and shared by the list, the CSV export and
the dashboard's links (ARCHITECTURE §8: "filters in the URL").

Collaborators: routes.py (query parameters → `LeadFilters`), service.list_leads, export.py.

Filters (design contract names, plus the part 3 additions):
  q              name contains, reference contains, or (digits only) the phone ends with them
  status         one stage
  project_id     a project's id, or `none` for general enquiries (addition: `none`)
  owner_id       a person's id, `me` (addition) or `unassigned`
  read           true = opened, false = unread
  source         one source
  utm_source, utm_medium, utm_campaign   exact tags; an empty value (`utm_campaign=`) = no tag
                 (+ source and medium: so each UTM report row has a matching inbox list)
  from, to       days in IST, both included, on the date the lead arrived
  include_spam   false (default) hides spam; `is_spam` (addition) true/false shows only spam /
                 only not spam and wins over include_spam
  include_sample true (default) shows seeded sample leads too (there are none in production)
  open           (addition) true = still being worked: not booked, lost or erased; false = the
                 rest. The dashboard's "unassigned" count links here with open=true.
SECURITY: the object-level rule is added on top by access.scope_leads, never by a filter.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Final

from sqlalchemy import ColumnElement, and_, func, not_, or_

from empire_api.leads.access import Staff
from empire_api.leads.models import Lead
from empire_api.leads.vocab import CLOSED_STATUSES
from empire_api.projects.common import escape_like
from empire_api.timeutil import IST

GENERAL: Final = "none"
ME: Final = "me"
UNASSIGNED: Final = "unassigned"
MIN_PHONE_DIGITS: Final = 3


@dataclass(frozen=True)
class LeadFilters:
    q: str | None = None
    status: str | None = None
    project_id: str | None = None
    owner_id: str | None = None
    read: bool | None = None
    source: str | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    include_spam: bool = False
    is_spam: bool | None = None
    include_sample: bool = True
    open: bool | None = None

    def query_params(self) -> dict[str, str]:
        """The filters as the inbox URL writes them (only those set), e.g. for dashboard links.
        INVARIANT: routes.lead_filters reads these back into the same LeadFilters (tested)."""
        names = {"date_from": "from", "date_to": "to"}
        defaults = asdict(LeadFilters())
        params: dict[str, str] = {}
        for key, value in asdict(self).items():
            if value == defaults[key]:
                continue
            if isinstance(value, bool):
                params[names.get(key, key)] = "true" if value else "false"
            elif isinstance(value, date):
                params[names.get(key, key)] = value.isoformat()
            else:
                params[names.get(key, key)] = str(value)
        return params

    def for_audit(self) -> dict[str, Any]:
        """The filters as the export's audit row records them (only those set).

        SECURITY.md §8: the search text is often a name or a phone number, so the audit row
        says only that a search was used and how long it was, never what it was.
        """
        values = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in asdict(self).items()}
        defaults = asdict(LeadFilters())
        found = {k: v for k, v in values.items() if v != defaults[k]}
        if self.q:
            found["q"] = f"[search: {len(self.q)} chars]"
        return found


def ist_day_start(day: date) -> datetime:
    """Midnight in India at the start of `day`, as an aware datetime (compares with UTC)."""
    return datetime.combine(day, time.min, tzinfo=IST)


def _search(q: str) -> ColumnElement[bool] | None:
    text = q.strip()
    if not text:
        return None
    lowered = f"%{escape_like(text.lower())}%"
    options: list[ColumnElement[bool]] = [func.lower(Lead.name).like(lowered, escape="\\")]
    compact = re.sub(r"\s", "", text).upper()
    if re.fullmatch(r"[A-Z0-9-]+", compact):
        options.append(Lead.reference.like(f"%{escape_like(compact)}%", escape="\\"))
    digits = re.sub(r"[\s\-+()]", "", text)
    if digits.isascii() and digits.isdigit() and len(digits) >= MIN_PHONE_DIGITS:
        options.append(Lead.phone_e164.like(f"%{digits}"))
    return or_(*options)


def _owner(value: str, staff: Staff) -> ColumnElement[bool]:
    if value == ME:
        return Lead.owner_user_id == staff.user_id
    if value == UNASSIGNED:
        return Lead.owner_user_id.is_(None)
    return Lead.owner_user_id == uuid.UUID(value)


def _who_and_what(filters: LeadFilters, staff: Staff) -> list[ColumnElement[bool]]:
    """Search, project, owner, read state, source and campaign."""
    found: list[ColumnElement[bool]] = []
    search = _search(filters.q) if filters.q else None
    if search is not None:
        found.append(search)
    if filters.project_id == GENERAL:
        found.append(Lead.project_id.is_(None))
    elif filters.project_id is not None:
        found.append(Lead.project_id == uuid.UUID(filters.project_id))
    if filters.owner_id is not None:
        found.append(_owner(filters.owner_id, staff))
    if filters.read is not None:
        found.append(Lead.read_at.is_not(None) if filters.read else Lead.read_at.is_(None))
    if filters.source is not None:
        found.append(Lead.source == filters.source)
    for column, value in (
        (Lead.utm_source, filters.utm_source),
        (Lead.utm_medium, filters.utm_medium),
        (Lead.utm_campaign, filters.utm_campaign),
    ):
        if value is not None:
            # An empty value means "no tag": the UTM report's null rows link here.
            found.append(column == value if value else column.is_(None))
    return found


def _when_and_kind(filters: LeadFilters) -> list[ColumnElement[bool]]:
    """Dates, spam and sample data."""
    found: list[ColumnElement[bool]] = []
    if filters.date_from is not None:
        found.append(Lead.created_at >= ist_day_start(filters.date_from))
    if filters.date_to is not None:
        found.append(Lead.created_at < ist_day_start(filters.date_to + timedelta(days=1)))
    if filters.is_spam is not None:
        found.append(Lead.is_spam.is_(filters.is_spam))
    elif not filters.include_spam:
        found.append(Lead.is_spam.is_(False))
    if not filters.include_sample:
        found.append(Lead.is_sample.is_(False))
    if filters.open is not None:
        still_open = and_(Lead.status.not_in(CLOSED_STATUSES), Lead.erased_at.is_(None))
        found.append(still_open if filters.open else not_(still_open))
    return found


def conditions(
    filters: LeadFilters, staff: Staff, *, with_status: bool = True
) -> list[ColumnElement[bool]]:
    """SQL conditions for `filters` (routes.py has already checked the id values)."""
    found = _who_and_what(filters, staff) + _when_and_kind(filters)
    if with_status and filters.status is not None:
        found.append(Lead.status == filters.status)
    return found
