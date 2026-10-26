"""The Auth, Settings and Users operations keep the design contract (handbook/api/openapi-v1.yaml,
D-020): same method, path, operationId and x-permission, every contract field present, enums and
filters only widened. Additions and the one deviation are listed here (Phase 4 part 5 report)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from test_leads_contract import _design, _enum, _fields

TAGS = {"Auth", "Settings", "Users"}
ADDED_OPERATIONS = {
    ("post", "/api/v1/auth/2fa/verify"): ("two_factor_verify", None),
    ("post", "/api/v1/auth/2fa/enrol"): ("two_factor_enrol_start", None),
    ("post", "/api/v1/auth/2fa/enrol/confirm"): ("two_factor_enrol_confirm", None),
    ("post", "/api/v1/auth/2fa/setup"): ("two_factor_setup_start", None),
    ("post", "/api/v1/auth/2fa/setup/confirm"): ("two_factor_setup_confirm", None),
    ("post", "/api/v1/auth/2fa/disable"): ("two_factor_disable", None),
    ("post", "/api/v1/auth/2fa/recovery-codes"): ("two_factor_recovery_codes", None),
    ("post", "/api/v1/admin/users/{id}/reset-2fa"): ("reset_user_two_factor", "users.manage"),
    ("get", "/api/v1/admin/permissions"): ("list_permissions", "users.manage"),
    ("get", "/api/v1/admin/consent-texts/current"): ("consent_text_kinds", "settings.read"),
}
# WHY (site_settings/routes.py): marketing must save tracking (marketing.tracking) and SEO
# defaults (seo.manage) without settings.write; each group checks its own permission inside.
CHANGED_PERMISSIONS = {
    ("patch", "/api/v1/admin/settings/{group}"): ("settings.write", "settings.read")
}
SCHEMAS = (
    "User",
    "UserInput",
    "Me",
    "AuditEntry",
    "FeatureFlag",
    "ConsentText",
    "ConsentTextInput",
    "Role",
    "LoginRequest",
    "PasswordForgot",
    "PasswordReset",
    "PasswordChange",
)


def _operations(spec: dict[str, Any]) -> dict[tuple[str, str], tuple[str, str | None]]:
    found = {}
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if isinstance(operation, dict) and TAGS & set(operation.get("tags", [])):
                found[(method, path)] = (operation["operationId"], operation.get("x-permission"))
    return found


def test_operations_match_the_design_contract(app: FastAPI) -> None:
    design = _operations(_design())
    live = _operations(app.openapi())
    assert len(design) == 22  # 6 auth, 7 settings (incl. consent texts and flags), 9 users
    expected = dict(design)
    for key, (contract, now) in CHANGED_PERMISSIONS.items():
        assert expected[key][1] == contract
        expected[key] = (expected[key][0], now)
    assert {k: v for k, v in live.items() if k not in ADDED_OPERATIONS} == expected
    for key, value in ADDED_OPERATIONS.items():
        assert live[key] == value, key


def test_the_settings_patch_publishes_its_permission_map(app: FastAPI) -> None:
    operation = app.openapi()["paths"]["/api/v1/admin/settings/{group}"]["patch"]
    assert operation["x-permission-by-group"]["tracking"] == "marketing.tracking"
    assert operation["x-permission-by-group"]["seo_defaults"].startswith("seo.manage")
    assert "super_admin" in operation["x-permission-by-group"]["privacy"]
    group = next(p for p in operation["parameters"] if p["name"] == "group")
    design = _design()["paths"]["/api/v1/admin/settings/{group}"]["patch"]["parameters"][0]
    assert set(design["schema"]["enum"]) | {"privacy"} == set(group["schema"]["enum"])


def test_every_contract_schema_keeps_its_fields(app: FastAPI) -> None:
    design = _design()["components"]["schemas"]
    live = app.openapi()["components"]["schemas"]
    for name in SCHEMAS:
        assert name in live, name
        missing = _fields(design, name) - _fields(live, name)
        assert not missing, (name, missing)


def test_role_enums_are_kept(app: FastAPI) -> None:
    design = _design()["components"]["schemas"]
    live = app.openapi()["components"]["schemas"]
    for name in ("User", "UserInput", "Role"):
        field = "key" if name == "Role" else "role"
        assert _enum(design[name]["properties"][field]) <= _enum(live[name]["properties"][field])


def test_the_audit_log_keeps_the_contract_filters(app: FastAPI) -> None:
    def names(spec: dict[str, Any]) -> set[str]:
        params = spec["paths"]["/api/v1/admin/audit-log"]["get"].get("parameters", [])
        return {p.get("name") or p["$ref"].rsplit("/", 1)[-1] for p in params}

    live = names(app.openapi())
    assert names(_design()) <= live
    assert {"system", "action_prefix"} <= live


def test_login_documents_the_two_factor_answer(app: FastAPI) -> None:
    responses = app.openapi()["paths"]["/api/v1/auth/login"]["post"]["responses"]
    assert responses["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/Me")
    assert responses["202"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/TwoFactorChallenge"
    )


def test_second_step_routes_are_public_and_rate_limited(app: FastAPI) -> None:
    paths = app.openapi()["paths"]
    for path in (
        "/api/v1/auth/2fa/verify",
        "/api/v1/auth/2fa/enrol",
        "/api/v1/auth/2fa/enrol/confirm",
    ):
        operation = paths[path]["post"]
        assert operation["x-public"] is True and operation["security"] == []
        assert "5 passwords or codes" in operation["x-rate-limit"]
    for path in (
        "/api/v1/auth/2fa/setup",
        "/api/v1/auth/2fa/disable",
        "/api/v1/auth/2fa/recovery-codes",
    ):
        assert paths[path]["post"]["x-auth"] == "signed_in"
