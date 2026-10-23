"""CSV export of the filtered inbox (`leads.export`, admin and super-admin; audited).

Collaborators: routes.py (GET /admin/leads/export.csv), filters.py, access.py, effects.py.
Implements: ARCHITECTURE §11 (export is audited), SECURITY.md §1 (same object-level rule as the
inbox), §8 (every export is audited), OWASP's CSV-injection advice.

How it works:
  1. Count the matching leads (same filters and object-level rule as the list). Above
     EXPORT_MAX_ROWS (50,000) the export is refused with "narrow the filters", never cut off.
  2. In one transaction, before any byte is sent: an audit row `lead.exported` with the filters
     and the row count, and an `exported` line on each exported lead's timeline. Commit. So an
     export that is interrupted half way is still on record.
  3. Stream the file in batches of 500 from a separate session (the request's session is gone
     once the response starts), with the cap as a hard LIMIT.

WHY a timeline line on every exported lead, even for a big export: it is one INSERT … SELECT
(no per-row round trips; about a second for 50,000 rows on the dev database), exports are rare
and admin-only, and DPDP accountability asks who took a person's data out of the system. The
lines don't count as work on the lead, so they never keep a lead from the retention clean-up.
Their ids are random (v4) rather than time-ordered (v7), because PostgreSQL 16 can't make v7;
the timeline orders by `created_at`, so nothing depends on it.

SECURITY (CSV injection): a text cell starting with = + - @, a tab or a carriage return gets a
leading apostrophe, so a spreadsheet shows it as text instead of running it as a formula. That
includes phone numbers (+91…): they open as '+91….
The file starts with a UTF-8 byte-order mark so Excel shows Hindi names correctly.

Columns, in order (COLUMNS below): reference, created_at (IST), name, phone, email, project,
configuration, source, status, lost_reason (code), lost_reason_note, owner, assigned_at, read_at,
last_activity_at (IST),
message, page_url, referrer, utm_source, utm_medium, utm_campaign, utm_term, utm_content, gclid,
gbraid, wbraid, fbclid, msclkid, preferred_bhk, budget_max_inr, preferred_contact_time,
language, consent_text_version, consented_at (IST), consent_note, marketing_consent (yes/no),
duplicate_of (reference), is_spam, is_sample, erased_at (IST).
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy import func, insert, literal, select
from sqlalchemy.orm import Session

from empire_api.db import get_sessionmaker
from empire_api.errors import ApiProblem
from empire_api.leads.access import Staff, owner_filter, scope_leads
from empire_api.leads.filters import LeadFilters, conditions
from empire_api.leads.models import Lead, LeadActivity, LeadConsent
from empire_api.leads.vocab import EXPORT_MAX_ROWS
from empire_api.platform import audit
from empire_api.projects import queries as project_queries
from empire_api.projects.common import jsonable
from empire_api.timeutil import IST, today_ist
from empire_api.users import directory

BATCH: Final = 500
TOO_MANY: Final = (
    "{count} leads match these filters; one export can hold at most {cap}. Narrow the dates or "
    "filters and export in parts."
)
_FORMULA_START: Final = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: Any) -> Any:
    """SECURITY: neutralise spreadsheet formulas in text cells (module header)."""
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return value


def _ist(moment: datetime | None) -> str:
    return moment.astimezone(IST).isoformat(timespec="seconds") if moment else ""


@dataclass
class _Batch:
    projects: dict[uuid.UUID, project_queries.ProjectRef]
    configurations: dict[uuid.UUID, str]
    owners: dict[uuid.UUID, str]
    consents: dict[tuple[uuid.UUID, str], LeadConsent]
    originals: dict[uuid.UUID, str]


Column = tuple[str, Callable[[Lead, _Batch], Any]]


def _consent(lead: Lead, batch: _Batch) -> LeadConsent | None:
    return batch.consents.get((lead.id, "lead_form"))


def _project(lead: Lead, batch: _Batch) -> str:
    ref = batch.projects.get(lead.project_id) if lead.project_id else None
    return ref.name if ref else ""


def _configuration(lead: Lead, batch: _Batch) -> str:
    return batch.configurations.get(lead.configuration_id, "") if lead.configuration_id else ""


def _owner(lead: Lead, batch: _Batch) -> str:
    return batch.owners.get(lead.owner_user_id, "") if lead.owner_user_id else ""


def _consent_version(lead: Lead, batch: _Batch) -> int | str:
    consent = _consent(lead, batch)
    return consent.version if consent and consent.version is not None else ""


def _consented_at(lead: Lead, batch: _Batch) -> str:
    consent = _consent(lead, batch)
    return _ist(consent.accepted_at) if consent else ""


def _consent_note(lead: Lead, batch: _Batch) -> str:
    consent = _consent(lead, batch)
    return (consent.consent_note or "") if consent else ""


def _duplicate_of(lead: Lead, batch: _Batch) -> str:
    return batch.originals.get(lead.duplicate_of_id, "") if lead.duplicate_of_id else ""


def _yes(value: bool) -> str:
    return "yes" if value else "no"


def _text(name: str) -> Column:
    return (name, lambda lead, _batch: getattr(lead, name) or "")


COLUMNS: Final[tuple[Column, ...]] = (
    ("reference", lambda lead, _b: lead.reference),
    ("created_at", lambda lead, _b: _ist(lead.created_at)),
    ("name", lambda lead, _b: lead.name),
    ("phone", lambda lead, _b: lead.phone_e164),
    _text("email"),
    ("project", _project),
    ("configuration", _configuration),
    ("source", lambda lead, _b: lead.source),
    ("status", lambda lead, _b: lead.status),
    _text("lost_reason"),
    _text("lost_reason_note"),
    ("owner", _owner),
    ("assigned_at", lambda lead, _b: _ist(lead.assigned_at)),
    ("read_at", lambda lead, _b: _ist(lead.read_at)),
    ("last_activity_at", lambda lead, _b: _ist(lead.last_activity_at)),
    _text("message"),
    _text("page_url"),
    _text("referrer"),
    _text("utm_source"),
    _text("utm_medium"),
    _text("utm_campaign"),
    _text("utm_term"),
    _text("utm_content"),
    _text("gclid"),
    _text("gbraid"),
    _text("wbraid"),
    _text("fbclid"),
    _text("msclkid"),
    ("preferred_bhk", lambda lead, _b: "" if lead.preferred_bhk is None else lead.preferred_bhk),
    ("budget_max_inr", lambda lead, _b: "" if lead.budget_max_inr is None else lead.budget_max_inr),
    _text("preferred_contact_time"),
    ("language", lambda lead, _b: lead.language),
    ("consent_text_version", _consent_version),
    ("consented_at", _consented_at),
    ("consent_note", _consent_note),
    ("marketing_consent", lambda lead, b: _yes((lead.id, "marketing") in b.consents)),
    ("duplicate_of", _duplicate_of),
    ("is_spam", lambda lead, _b: _yes(lead.is_spam)),
    ("is_sample", lambda lead, _b: _yes(lead.is_sample)),
    ("erased_at", lambda lead, _b: _ist(lead.erased_at)),
)
HEADER: Final = tuple(name for name, _ in COLUMNS)


def _matching(staff: Staff, filters: LeadFilters) -> Any:
    return scope_leads(select(Lead).where(*conditions(filters, staff)), staff)


def prepare(db: Session, staff: Staff, filters: LeadFilters) -> int:
    """Steps 1–2 (module header). Returns how many rows the file will hold."""
    stmt = _matching(staff, filters)
    count = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)  # 1
    if count > EXPORT_MAX_ROWS:
        raise ApiProblem(422, TOO_MANY.format(count=f"{count:,}", cap=f"{EXPORT_MAX_ROWS:,}"))
    row = audit.record(  # 2
        db,
        action="lead.exported",
        entity_type="lead",
        entity_id="export",
        actor_id=staff.user_id,
        ip=staff.ip,
        changes={"filters": [None, jsonable(filters.for_audit())], "rows": [None, count]},
    )
    db.flush()
    ids = stmt.with_only_columns(Lead.id).order_by(None).subquery()
    db.execute(
        insert(LeadActivity).from_select(
            ["id", "lead_id", "kind", "actor_user_id", "data"],
            select(
                func.gen_random_uuid(),
                ids.c.id,
                literal("exported"),
                literal(staff.user_id),
                func.jsonb_build_object("audit_id", row.id, "rows", count),
            ),
        )
    )
    db.commit()
    return count


def _originals(db: Session, ids: set[uuid.UUID], staff: Staff) -> dict[uuid.UUID, str]:
    """SECURITY.md §1: the `duplicate_of` column names only leads this staff member may open."""
    if not ids:
        return {}
    stmt = select(Lead.id, Lead.reference).where(Lead.id.in_(ids))
    owner = owner_filter(staff)
    if owner is not None:
        stmt = stmt.where(Lead.owner_user_id == owner)
    return dict(db.execute(stmt).all())


def _load_batch(db: Session, leads: Sequence[Lead], staff: Staff) -> _Batch:
    ids = [lead.id for lead in leads]
    originals_ids = {lead.duplicate_of_id for lead in leads if lead.duplicate_of_id}
    return _Batch(
        projects=project_queries.project_refs(db, (lead.project_id for lead in leads)),
        configurations=project_queries.configuration_names(
            db, (lead.configuration_id for lead in leads)
        ),
        owners={
            user_id: ref.name
            for user_id, ref in directory.user_refs(
                db, (lead.owner_user_id for lead in leads)
            ).items()
        },
        consents={
            (c.lead_id, c.kind): c
            for c in db.scalars(select(LeadConsent).where(LeadConsent.lead_id.in_(ids)))
        },
        originals=_originals(db, originals_ids, staff),
    )


def _line(values: Sequence[Any]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\r\n").writerow([safe_cell(v) for v in values])
    return buffer.getvalue()


def stream(staff: Staff, filters: LeadFilters) -> Iterator[str]:
    """Step 3: the file, line by line, newest lead first (own session; read-only)."""
    yield "﻿" + _line(HEADER)
    with get_sessionmaker()() as db:
        result = db.scalars(
            _matching(staff, filters)
            .order_by(Lead.created_at.desc(), Lead.id.desc())
            .limit(EXPORT_MAX_ROWS)
            .execution_options(yield_per=BATCH)
        )
        for chunk in result.partitions():
            batch = _load_batch(db, chunk, staff)
            yield "".join(_line([get(lead, batch) for _, get in COLUMNS]) for lead in chunk)


def filename() -> str:
    return f"empire-leads-{today_ist().isoformat()}.csv"
