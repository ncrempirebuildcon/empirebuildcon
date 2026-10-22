"""Page/per-page helpers shared by list endpoints (design contract: max 100 per page)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Query

MAX_PER_PAGE = 100


@dataclass(frozen=True)
class PageParams:
    page: int
    per_page: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    def meta(self, total: int) -> dict[str, int]:
        pages = (total + self.per_page - 1) // self.per_page if total else 0
        return {"page": self.page, "per_page": self.per_page, "total": total, "pages": pages}


def page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=MAX_PER_PAGE)] = 20,
) -> PageParams:
    return PageParams(page=page, per_page=per_page)
