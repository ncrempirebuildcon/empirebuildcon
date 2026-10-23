"""The FastAPI application factory. Run locally: `uv run uvicorn empire_api.main:app --reload`.

Implements: ARCHITECTURE §3 (no redirects, same-origin API under /api), SECURITY.md §3–4.

Middleware order (outermost first): trailing-slash strip → security headers → request id/log
and the 500 safety net → edge guard (only our web proxy may call us) → CORS (development only).
The strip must run first so every later layer sees the final path; security headers sit outside
the 500 safety net and the edge guard so their answers carry the headers too.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from empire_api import health
from empire_api.config import Settings, get_settings
from empire_api.content import routes as content_routes
from empire_api.dashboard import routes as dashboard_routes
from empire_api.errors import PROBLEM_MEDIA_TYPE, register_error_handlers
from empire_api.integrations import routes as internal_routes
from empire_api.leads import routes as lead_routes
from empire_api.leads import routes_public as lead_public_routes
from empire_api.leads import routes_visits as lead_visit_routes
from empire_api.logs import configure_logging
from empire_api.media import routes as media_routes
from empire_api.media import routes_dev as media_dev_routes
from empire_api.middleware.edge_guard import EdgeGuardMiddleware
from empire_api.middleware.request_context import RequestContextMiddleware
from empire_api.middleware.security_headers import SecurityHeadersMiddleware
from empire_api.middleware.trailing_slash import StripTrailingSlashMiddleware
from empire_api.observability import init_sentry
from empire_api.projects import routes as project_routes
from empire_api.projects import routes_catalogue, routes_children
from empire_api.site_settings import routes as settings_routes
from empire_api.users import routes_admin, routes_auth

_DESCRIPTION = (
    "Empire website and CMS API. The browser calls `/api/*` on the site and Next.js forwards "
    "it here. Errors are RFC 9457 problem+json. Staff calls use the `__Host-empire_session` "
    "cookie; writes also send `X-CSRF-Token` (from `/api/v1/auth/me`). `x-permission` names the "
    "permission an operation needs (handbook/ARCHITECTURE.md §11)."
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()
    init_sentry(settings, component="api")
    show_docs = not settings.is_production_like
    app = FastAPI(
        title="Empire API",
        version=settings.version,
        description=_DESCRIPTION,
        # DO NOT CHANGE: see middleware/trailing_slash.py; redirects broke sessions before.
        redirect_slashes=False,
        docs_url="/api/docs" if show_docs else None,
        redoc_url=None,
        swagger_ui_oauth2_redirect_url=None,
        openapi_url="/api/openapi.json" if show_docs else None,
    )
    register_error_handlers(app)
    for router in (
        health.router,
        routes_auth.router,
        routes_admin.router,
        settings_routes.router,
        project_routes.router,
        routes_children.router,
        routes_catalogue.router,
        media_routes.router,
        lead_public_routes.router,
        lead_routes.router,
        lead_visit_routes.router,
        dashboard_routes.router,
        content_routes.router,
        internal_routes.router,
    ):
        app.include_router(router)
    if settings.media_store_kind == "fake":
        # SECURITY: the fake store's file and upload routes exist only while it is active,
        # which config.py refuses in staging and production (D-033).
        app.include_router(media_dev_routes.router)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
            allow_headers=["Content-Type", "X-CSRF-Token"],
        )
    # add_middleware wraps the app, so the LAST one added is the OUTERMOST.
    app.add_middleware(EdgeGuardMiddleware, edge_key=settings.edge_proxy_key.get_secret_value())
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production_like)
    app.add_middleware(StripTrailingSlashMiddleware)

    _install_openapi(app)
    return app


def _install_openapi(app: FastAPI) -> None:
    """Add the security schemes from the design contract to the generated spec."""

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        original = FastAPI.openapi(app)
        components = original.setdefault("components", {})
        components["securitySchemes"] = {
            "cookieAuth": {"type": "apiKey", "in": "cookie", "name": "__Host-empire_session"},
            "csrfHeader": {"type": "apiKey", "in": "header", "name": "X-CSRF-Token"},
            "internalKey": {
                "type": "apiKey",
                "in": "header",
                "name": "X-Internal-Key",
                "description": "Shared secret for scheduler → API calls. Env INTERNAL_API_KEY.",
            },
        }
        components.setdefault("schemas", {}).update(media_routes.openapi_components())
        _problem_media_type(original)
        # FastAPI always adds its own validation-error schemas; our 422s are Problem objects.
        for unused in ("HTTPValidationError", "ValidationError"):
            components.get("schemas", {}).pop(unused, None)
        original["servers"] = [
            {"url": "https://empirebuildcon.com", "description": "Production (via the site)"},
            {"url": "http://localhost:3000", "description": "Local web app (proxies /api)"},
        ]
        app.openapi_schema = original
        return original

    app.openapi = custom_openapi  # type: ignore[method-assign]


def _problem_media_type(spec: dict[str, Any]) -> None:
    """Error responses are served as application/problem+json; say so in the spec."""
    for item in spec.get("paths", {}).values():
        for operation in item.values():
            if not isinstance(operation, dict):
                continue
            for status, response in operation.get("responses", {}).items():
                content = response.get("content", {})
                if status.isdigit() and int(status) >= 400 and "application/json" in content:
                    content[PROBLEM_MEDIA_TYPE] = content.pop("application/json")
                schema = content.get(PROBLEM_MEDIA_TYPE, {}).get("schema", {})
                if schema.get("$ref", "").endswith("/HTTPValidationError"):
                    # WHY: FastAPI's default 422 points at HTTPValidationError, which we remove
                    # (our handler answers with Problem); a dangling $ref breaks client generation.
                    schema["$ref"] = "#/components/schemas/Problem"


app = create_app()
