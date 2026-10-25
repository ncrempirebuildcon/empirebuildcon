"""Tables of the SEO module: `redirect` (ARCHITECTURE §16, design contract schema Redirect).

Collaborators: migrations/versions/0005_content.py creates the table (tests/test_migrations.py
fails on any drift); seo/redirects.py is the only writer.

INVARIANT: one redirect per `from_path` (unique), never to itself, 301 or 308 only. The service
also keeps every active redirect one hop long (no chains, no loops; redirects.py).
SECURITY (SECURITY.md §5, review H1): `to_path` is the `Location` the website sends, so it is a
path on our site: it starts with one `/` and has no backslash (`ck_redirect_to_path_is_site_path`,
a backstop for seo/paths.normalise_target). `//host` or a backslash would send visitors elsewhere.
`hits` and `last_hit_at` are written by the web app's redirect middleware in Phase 5.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import BigInteger, CheckConstraint, SmallInteger, String, func
from sqlalchemy import text as sql
from sqlalchemy.orm import Mapped, mapped_column

from empire_api.db import Base, created_at_column, uuid_pk
from empire_api.projects.vocab import check_in
from empire_api.seo.vocab import REDIRECT_ORIGINS

# DO NOT CHANGE without the same change in migrations/versions/0005_content.py (SECURITY.md §5).
TO_PATH_IS_SITE_PATH: Final = (
    "left(to_path, 1) = '/' AND left(to_path, 2) <> '//' AND strpos(to_path, '\\') = 0"
)


class Redirect(Base):
    __tablename__ = "redirect"

    id: Mapped[uuid.UUID] = uuid_pk()
    from_path: Mapped[str] = mapped_column(String(500), unique=True)
    to_path: Mapped[str] = mapped_column(String(500))
    status_code: Mapped[int] = mapped_column(SmallInteger, server_default=sql("308"))
    is_active: Mapped[bool] = mapped_column(server_default=sql("true"))
    origin: Mapped[str] = mapped_column(String(10), server_default=sql("'manual'"))
    # TODO(phase-5): the redirect middleware counts these; nothing writes them before then.
    hits: Mapped[int] = mapped_column(BigInteger, server_default=sql("0"))
    last_hit_at: Mapped[datetime | None] = mapped_column()
    # WHY no foreign keys: like project.created_by, authorship outlives any staff account row.
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    updated_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("status_code IN (301, 308)", name="status_code_valid"),
        CheckConstraint(check_in("origin", REDIRECT_ORIGINS), name="origin_valid"),
        CheckConstraint("left(from_path, 1) = '/'", name="from_path_is_path"),
        CheckConstraint(TO_PATH_IS_SITE_PATH, name="to_path_is_site_path"),
        CheckConstraint("from_path <> to_path", name="not_to_itself"),
        CheckConstraint("hits >= 0", name="hits_not_negative"),
    )
