"""Request and response shapes of the SEO module (design contract schemas Redirect and
RedirectInput), plus `SeoWarning` (the CMS checklist line on pages and posts).

Additions to the contract (D-035): `RedirectUpdate` for PATCH (every field optional, like
ProjectUpdate in D-031); on Redirect `origin` (manual, or made by a page/post/project slug
change), `notices` (what the save changed besides this row, e.g. a collapsed chain), and
`created_at`/`updated_at`.

SECURITY (SECURITY.md §5): unknown fields are refused; `to_path` is a site path or an address on
our own domains (seo/paths.py), never another host.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, Field, StringConstraints, field_validator
from pydantic_core import PydanticCustomError

from empire_api.projects.fields import OutModel, SchemaExtra, StrictModel
from empire_api.seo.paths import normalise_from_path, normalise_target
from empire_api.seo.vocab import MAX_PATH, RedirectOrigin, RedirectStatus
from empire_api.users.schemas import PageMeta

FromPath = Annotated[
    str,
    StringConstraints(min_length=1, max_length=MAX_PATH),
    AfterValidator(normalise_from_path),
    SchemaExtra({"pattern": "^/"}),
]
ToPath = Annotated[
    str, StringConstraints(min_length=1, max_length=MAX_PATH), AfterValidator(normalise_target)
]


class SeoWarning(OutModel):
    """One line of the SEO checklist. Warnings never block saving or publishing."""

    code: str = Field(examples=["title_missing", "description_long"])
    field: str = Field(examples=["seo.title"])
    message: str


class Redirect(OutModel):
    id: uuid.UUID
    from_path: str = Field(pattern="^/")
    to_path: str
    status_code: RedirectStatus
    is_active: bool
    origin: RedirectOrigin = Field(
        description="manual, or made automatically when a live page, post or project was renamed"
    )
    hits: Annotated[int, SchemaExtra({"readOnly": True})] = Field(
        description="Counted by the website from Phase 5"
    )
    last_hit_at: datetime | None
    notices: list[str] = Field(
        description="What this save also changed, e.g. a chain collapsed; empty in lists"
    )
    created_at: datetime
    updated_at: datetime


class RedirectList(OutModel):
    items: list[Redirect]
    meta: PageMeta


class RedirectInput(StrictModel):
    """A new redirect. A trailing / is dropped; an https address on our domains is stored as
    its path. 308 unless you choose 301."""

    from_path: FromPath
    to_path: ToPath
    status_code: RedirectStatus = "308"
    is_active: bool = True


class RedirectUpdate(StrictModel):
    """PATCH: send only what changes."""

    from_path: FromPath | None = None
    to_path: ToPath | None = None
    status_code: RedirectStatus | None = None
    is_active: bool | None = None

    @field_validator("from_path", "to_path", "status_code", "is_active")
    @classmethod
    def _not_null(cls, value: Any) -> Any:
        if value is None:
            raise PydanticCustomError("not_null", "This can't be empty.")
        return value
