"""RFC 9457 problem+json errors for every failure (design contract: "Errors use RFC 9457").

Collaborators: main.py registers the handlers; services raise `ApiProblem`.

SECURITY: the 500 handler never returns exception text or stack traces to the client; it logs
them with the request id so support can find the details.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from empire_api.logs import get_logger

PROBLEM_MEDIA_TYPE = "application/problem+json"

_TITLES = {
    400: "Bad request",
    401: "Not signed in",
    403: "Not allowed",
    404: "Not found",
    405: "Method not allowed",
    409: "Conflict",
    413: "Too large",
    415: "Unsupported media type",
    422: "Invalid input",
    429: "Too many requests",
    500: "Something went wrong",
    503: "Service unavailable",
}

log = get_logger(__name__)


class ProblemField(BaseModel):
    field: str
    message: str


class Problem(BaseModel):
    """RFC 9457 problem details. Every error uses this shape (design contract schema)."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    errors: list[ProblemField] | None = None


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """`responses=` entries so the OpenAPI spec (and the typed web client) know the error shape.

    main.py moves these from application/json to application/problem+json in the spec.
    """
    return {s: {"model": Problem, "description": _TITLES.get(s, "Error")} for s in statuses}


class ApiProblem(Exception):  # noqa: N818 — reads better at call sites than "ApiProblemError"
    """Raise anywhere in a request to answer with a problem+json body.

    `detail` is shown to staff and visitors, so write it as a plain sentence they can act on.
    """

    def __init__(
        self,
        status: int,
        detail: str,
        *,
        title: str | None = None,
        type_: str = "about:blank",
        headers: dict[str, str] | None = None,
        errors: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.title = title or _TITLES.get(status, "Error")
        self.type = type_
        self.headers = headers or {}
        self.errors = errors


def problem_response(
    request: Request,
    status: int,
    detail: str,
    *,
    title: str | None = None,
    type_: str = "about:blank",
    headers: dict[str, str] | None = None,
    errors: list[dict[str, str]] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": type_,
        "title": title or _TITLES.get(status, "Error"),
        "status": status,
        "detail": detail,
        "instance": request.url.path,
    }
    if errors:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, headers=headers, media_type=PROBLEM_MEDIA_TYPE)


def _field_name(loc: tuple[Any, ...]) -> str:
    """('body', 'email') → 'email'; ('query', 'page') → 'page'. Keeps nested paths dotted."""
    parts = [str(p) for p in loc if p not in ("body", "query", "path", "header", "cookie")]
    return ".".join(parts) or "request"


async def _api_problem(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiProblem)  # noqa: S101 — registered for this type only
    return problem_response(
        request,
        exc.status,
        exc.detail,
        title=exc.title,
        type_=exc.type,
        headers=exc.headers,
        errors=exc.errors,
    )


async def _http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    detail = exc.detail if isinstance(exc.detail, str) else _TITLES.get(exc.status_code, "Error")
    if exc.status_code == 404 and detail == "Not Found":
        detail = "There is nothing at this address."
    if exc.status_code == 405 and detail == "Method Not Allowed":
        detail = "This address does not accept that method."
    return problem_response(request, exc.status_code, detail, headers=dict(exc.headers or {}))


async def _validation(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    errors = [{"field": _field_name(tuple(e["loc"])), "message": e["msg"]} for e in exc.errors()]
    return problem_response(request, 422, "Some fields need attention.", errors=errors)


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_error", error_type=type(exc).__name__)
    return problem_response(
        request, 500, "Something went wrong on our side. Please try again in a minute."
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiProblem, _api_problem)
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation)
    app.add_exception_handler(Exception, _unhandled)
