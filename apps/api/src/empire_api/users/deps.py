"""FastAPI dependencies for signed-in staff and permissions, plus OpenAPI route markers.

How to protect a route (also in apps/api/README.md):

    @router.get("/admin/things", **staff("things.read"))
    def list_things(actor: Annotated[SessionInfo, Depends(require("things.read"))]) -> ...

`staff()` adds `x-permission` to the OpenAPI operation; `require()` enforces it. The route
walker test fails if a route has neither `x-permission`, `x-auth`, `x-public` nor `x-internal`.

SECURITY: `require()` is the only gate. The CMS hiding a button is a convenience, not security
(SECURITY.md §2). Unsafe methods (POST/PUT/PATCH/DELETE) also need a matching X-CSRF-Token.
"""

from __future__ import annotations

from functools import cache
from typing import Annotated, Any

import structlog
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from empire_api.db import get_db
from empire_api.errors import ApiProblem
from empire_api.users.roles import has_permission
from empire_api.users.sessions import COOKIE_NAME, SessionInfo, csrf_matches, resolve_session

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_COOKIE_SECURITY: list[dict[str, list[str]]] = [{"cookieAuth": []}]
_COOKIE_CSRF_SECURITY: list[dict[str, list[str]]] = [{"cookieAuth": [], "csrfHeader": []}]


def staff(permission: str, *, write: bool = False) -> dict[str, Any]:
    """Route kwargs marking a staff route with its permission in the OpenAPI spec."""
    return {
        "openapi_extra": {
            "x-permission": permission,
            "security": _COOKIE_CSRF_SECURITY if write else _COOKIE_SECURITY,
        }
    }


def signed_in_route(*, write: bool = False) -> dict[str, Any]:
    """Route kwargs for routes any signed-in staff member may use (me, logout, own password)."""
    return {
        "openapi_extra": {
            "x-auth": "signed_in",
            "security": _COOKIE_CSRF_SECURITY if write else _COOKIE_SECURITY,
        }
    }


PUBLIC: dict[str, Any] = {"openapi_extra": {"x-public": True, "security": []}}
INTERNAL: dict[str, Any] = {
    "openapi_extra": {"x-internal": True, "security": [{"internalKey": []}]}
}


def current_session(request: Request, db: Annotated[Session, Depends(get_db)]) -> SessionInfo:
    """The signed-in staff member, or 401. Checks CSRF on unsafe methods."""
    info = resolve_session(db, request.cookies.get(COOKIE_NAME))
    if info is None:
        raise ApiProblem(401, "Please sign in to continue.")
    if request.method not in _SAFE_METHODS and not csrf_matches(
        info.session.id, request.headers.get("x-csrf-token")
    ):
        raise ApiProblem(403, "Your session token is missing or out of date. Reload the page.")
    structlog.contextvars.bind_contextvars(user_id=str(info.user.id))
    return info


@cache
def require(permission: str) -> Any:
    """Dependency factory: signed in AND the role has `permission`, else 401/403.

    WHY @cache: FastAPI de-duplicates a dependency per request by the callable's identity, so
    returning the same function for the same permission avoids checking twice.
    """

    def dependency(
        info: Annotated[SessionInfo, Depends(current_session)],
    ) -> SessionInfo:
        if not has_permission(info.user.role, permission):
            raise ApiProblem(403, "Your role doesn't allow this.")
        return info

    dependency.__name__ = f"require_{permission.replace('.', '_')}"
    return dependency


CurrentSession = Annotated[SessionInfo, Depends(current_session)]
DbSession = Annotated[Session, Depends(get_db)]
