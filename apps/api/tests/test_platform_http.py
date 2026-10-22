"""HTTP platform behaviour: health, no redirects, route markers, headers, problem+json."""

from __future__ import annotations

import re
import uuid
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from empire_api import health as health_module
from empire_api.config import Settings
from empire_api.main import create_app
from empire_api.users.roles import PERMISSIONS

MARKERS = ("x-permission", "x-auth", "x-public", "x-internal")


def _operations(app: FastAPI) -> list[tuple[str, str, dict[str, Any]]]:
    """(method, path, operation) for every documented route.

    WHY the OpenAPI spec and not `app.routes`: FastAPI 0.15x keeps included routers as lazy
    wrappers, so `app.routes` no longer lists the API routes. The spec is the public view.
    """
    spec = app.openapi()
    return [
        (method.upper(), path, op)
        for path, item in spec["paths"].items()
        for method, op in item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


def test_live_needs_no_database(client: TestClient) -> None:
    response = client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_checks_database(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["version"]


def test_health_reports_database_down(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class Broken:
        def connect(self) -> None:
            raise RuntimeError("database unreachable")

    monkeypatch.setattr(health_module, "get_engine", Broken)
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["database"] == "down"


def test_no_route_ever_redirects(app: FastAPI, client: TestClient) -> None:
    """DO NOT DELETE: guards the Current Investor production bug (ARCHITECTURE §3)."""
    checked = 0
    for method, template, _op in _operations(app):
        path = _concrete(template)
        for variant in (path, path + "/"):
            response = client.request(method, variant)
            assert not 300 <= response.status_code < 400, (method, variant)
            checked += 1
    assert checked >= 40


def test_every_route_declares_who_may_call_it(app: FastAPI) -> None:
    operations = _operations(app)
    assert len(operations) >= 20
    for method, path, op in operations:
        assert any(m in op for m in MARKERS), f"{method} {path} has no permission marker"
        if "x-permission" in op:
            assert op["x-permission"] in PERMISSIONS, path


def test_openapi_lists_permissions_and_security(app: FastAPI) -> None:
    spec = app.openapi()
    assert "cookieAuth" in spec["components"]["securitySchemes"]
    op = spec["paths"]["/api/v1/admin/audit-log"]["get"]
    assert op["x-permission"] == "audit.read"
    assert spec["paths"]["/api/v1/auth/login"]["post"]["x-public"] is True


def test_security_headers_on_api_responses(client: TestClient) -> None:
    response = client.get("/api/health/live")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert "strict-transport-security" not in response.headers  # not production-like
    assert response.headers["x-request-id"]


def test_staff_routes_are_never_cached(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_hsts_and_hidden_docs_in_production() -> None:
    settings = Settings(
        app_env="production",
        session_secret=SecretStr("s" * 48),
        internal_api_key=SecretStr("i" * 48),
        ip_hash_salt=SecretStr("p" * 48),
        data_encryption_key=SecretStr(Fernet.generate_key().decode()),
    )
    prod = create_app(settings)
    with TestClient(prod, base_url="https://testserver") as c:
        response = c.get("/api/health/live")
        assert response.headers["strict-transport-security"].startswith("max-age=31536000")
        assert c.get("/api/openapi.json").status_code == 404
        assert c.get("/api/docs").status_code == 404


def test_production_refuses_placeholder_secrets() -> None:
    with pytest.raises(ValueError, match="placeholder"):
        Settings(app_env="production", session_secret=SecretStr("change-me-to-something-long-xx"))


def test_problem_json_for_unknown_paths(client: TestClient) -> None:
    response = client.get("/api/v1/nothing-here")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 404
    assert body["title"] == "Not found"
    assert body["instance"] == "/api/v1/nothing-here"


def test_validation_errors_list_fields(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"email": "not-an-email"})
    assert response.status_code == 422
    fields = {e["field"] for e in response.json()["errors"]}
    assert {"email", "password"} <= fields


def test_spec_describes_errors_as_problem_json(app: FastAPI) -> None:
    spec = app.openapi()
    assert "HTTPValidationError" not in spec["components"]["schemas"]
    login = spec["paths"]["/api/v1/auth/login"]["post"]["responses"]
    assert set(login["422"]["content"]) == {"application/problem+json"}
    assert set(login["200"]["content"]) == {"application/json"}


def test_openapi_has_no_dangling_refs(client: TestClient) -> None:
    """Every $ref in the published spec resolves, so the TypeScript client can be generated."""
    spec = client.get("/api/openapi.json").json()
    refs: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "$ref" and isinstance(value, str):
                    refs.add(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(spec)
    schemas = spec["components"]["schemas"]
    assert all(ref.rsplit("/", 1)[-1] in schemas for ref in refs if "/schemas/" in ref)
