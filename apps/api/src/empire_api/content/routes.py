"""Consent-text endpoints: /api/v1/admin/consent-texts (design contract tag "Settings").

HTTP only: the rules are in consent.py. Permissions (ARCHITECTURE §11): reading needs
`settings.read`; writing a draft and publishing need `legal.publish`.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.orm import Session

from empire_api.content import consent
from empire_api.content.models import ConsentText as ConsentRow
from empire_api.content.schemas import ConsentKindSummary, ConsentText, ConsentTextInput
from empire_api.content.vocab import ConsentKind
from empire_api.db import get_db
from empire_api.errors import problem_responses
from empire_api.platform.crypto import client_ip
from empire_api.projects.common import Actor
from empire_api.users import directory
from empire_api.users.deps import require, staff
from empire_api.users.sessions import SessionInfo

router = APIRouter(
    prefix="/api/v1/admin", tags=["Settings"], responses=problem_responses(401, 403, 404, 422)
)
Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[SessionInfo, Depends(require("settings.read"))]
Publisher = Annotated[SessionInfo, Depends(require("legal.publish"))]
TextId = Annotated[uuid.UUID, Path(alias="id")]


def _out(db: Session, rows: list[ConsentRow]) -> list[ConsentText]:
    people = directory.user_refs(db, [r.created_by for r in rows] + [r.published_by for r in rows])
    return [
        ConsentText(
            id=row.id,
            kind=row.kind,
            version=row.version,
            body=row.body,
            checkbox_label=row.checkbox_label,
            published_at=row.published_at,
            is_current=row.is_current,
            is_draft=consent.is_draft(row),
            is_draft_text=consent.is_draft(row),
            created_at=row.created_at,
            created_by=people.get(row.created_by) if row.created_by else None,
            published_by=people.get(row.published_by) if row.published_by else None,
        )
        for row in rows
    ]


# The purpose of each kind, in plain English, for the consent-text screen.
KIND_TEXT: Final[dict[str, tuple[str, str]]] = {
    "lead_form": ("Enquiry forms", "Required on every enquiry, site-visit and brochure form."),
    "marketing": (
        "Marketing (optional)",
        "The separate, unticked box for news and offers; never assumed.",
    ),
    "brochure": ("Brochure requests", "Reserved: brochure forms use the enquiry text for now."),
    "cookies": ("Cookie banner", "Phase 6: the consent banner for analytics and marketing tags."),
    "chat": ("Chat assistant", "Phase 7: shown before the chat assistant takes details."),
}


@router.get(
    "/consent-texts/current",
    response_model=list[ConsentKindSummary],
    operation_id="consent_text_kinds",
    summary="Each purpose with its current version (contract addition, part 5)",
    **staff("settings.read"),
)
def consent_text_kinds(actor: Reader, db: Db) -> list[ConsentKindSummary]:
    """Every purpose, even one with no text yet, with the version the forms show now."""
    found = []
    for item in consent.kinds_summary(db):
        current = _out(db, [item.current])[0] if item.current else None
        latest_version = item.latest.version if item.latest else None
        label, purpose = KIND_TEXT.get(item.kind, (item.kind, ""))
        found.append(
            ConsentKindSummary(
                kind=item.kind,
                label=label,
                purpose=purpose,
                current=current,
                current_version=current.version if current else None,
                latest_version=latest_version,
                versions=item.versions,
                has_unpublished_newer=bool(
                    latest_version
                    and (current is None or latest_version > current.version)
                    and item.latest is not None
                    and item.latest.published_at is None
                ),
            )
        )
    return found


@router.get(
    "/consent-texts",
    response_model=list[ConsentText],
    operation_id="list_consent_texts",
    summary="All versions",
    **staff("settings.read"),
)
def list_consent_texts(actor: Reader, db: Db, kind: ConsentKind | None = None) -> list[ConsentText]:
    """Every version of every kind (or of one `kind`), newest version first."""
    return _out(db, consent.list_texts(db, kind))


@router.post(
    "/consent-texts",
    status_code=201,
    response_model=ConsentText,
    operation_id="create_consent_text",
    summary="New draft version",
    **staff("legal.publish", write=True),
)
def create_consent_text(
    body: ConsentTextInput, actor: Publisher, request: Request, db: Db
) -> ConsentText:
    """A new, unpublished version. It takes effect only when published."""
    row = consent.create_draft(
        db,
        body.kind,
        body.body,
        body.checkbox_label,
        Actor(user_id=actor.user.id, ip=client_ip(request)),
    )
    return _out(db, [row])[0]


@router.post(
    "/consent-texts/{id}/publish",
    response_model=ConsentText,
    operation_id="publish_consent_text",
    summary="Make this version current",
    responses=problem_responses(409),
    **staff("legal.publish", write=True),
)
def publish_consent_text(
    text_id: TextId, actor: Publisher, request: Request, db: Db
) -> ConsentText:
    """Forms must send this version's id from now on; older versions get 409 "reload".
    In production a text still marked as a draft is refused (409)."""
    row = consent.publish(db, text_id, Actor(user_id=actor.user.id, ip=client_ip(request)))
    return _out(db, [row])[0]
