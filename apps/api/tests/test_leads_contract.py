"""The leads, dashboard and consent-text operations keep the design contract
(handbook/api/openapi-v1.yaml, D-020): same method, path, operationId and x-permission, every
contract schema and field present (additions allowed, renames listed), enums only widened."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # PyYAML comes with uvicorn[standard]
from fastapi import FastAPI

CONTRACT = Path(__file__).resolve().parents[3] / "handbook" / "api" / "openapi-v1.yaml"
TAGS = {"Lead intake", "Leads", "Dashboard"}
CONSENT_PATHS = ("/api/v1/admin/consent-texts", "/api/v1/admin/consent-texts/{id}/publish")
# Contract additions (Phase 4 part 3 report).
ADDED_OPERATIONS = {("get", "/api/v1/admin/lead-owners"): ("list_lead_owners", "leads.read")}
RENAMED_FIELDS = {"Lead": {"is_test": "is_sample"}}
SCHEMAS = (
    "Lead",
    "LeadCreate",
    "LeadManualCreate",
    "LeadUpdate",
    "LeadNote",
    "LeadNoteInput",
    "LeadActivity",
    "LeadAccepted",
    "ConsentGiven",
    "ConsentText",
    "ConsentTextInput",
    "SiteVisit",
    "SiteVisitRequest",
    "SiteVisitUpdate",
    "Dashboard",
    "DashboardCount",
    "UtmReportRow",
    "BrochureRequest",
    "BrochureLink",
)


def _design() -> dict[str, Any]:
    return dict(yaml.safe_load(CONTRACT.read_text()))


def _operations(spec: dict[str, Any]) -> dict[tuple[str, str], tuple[str, str | None]]:
    found = {}
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if not isinstance(operation, dict):
                continue
            if TAGS & set(operation.get("tags", [])) or path in CONSENT_PATHS:
                found[(method, path)] = (operation["operationId"], operation.get("x-permission"))
    return found


def _fields(schemas: dict[str, Any], name: str) -> set[str]:
    schema = schemas[name]
    found = set(schema.get("properties", {}))
    for part in schema.get("allOf", []):
        found |= (
            _fields(schemas, part["$ref"].rsplit("/", 1)[-1])
            if "$ref" in part
            else set(part.get("properties", {}))
        )
    return found


def _enum(schema: dict[str, Any]) -> set[str]:
    if "enum" in schema:
        return set(schema["enum"])
    for option in schema.get("anyOf", []):
        if "enum" in option:
            return set(option["enum"])
    return set()


def test_operations_match_the_design_contract(app: FastAPI) -> None:
    design = _operations(_design())
    live = _operations(app.openapi())
    assert len(design) == 21  # 3 intake, 1 dashboard, 14 leads and visits, 3 consent texts
    assert {key: value for key, value in live.items() if key not in ADDED_OPERATIONS} == design
    for key, value in ADDED_OPERATIONS.items():
        assert live[key] == value


def test_every_contract_schema_exists_with_its_fields(app: FastAPI) -> None:
    design = _design()["components"]["schemas"]
    live = app.openapi()["components"]["schemas"]
    for name in SCHEMAS:
        assert name in live, name
        renamed = RENAMED_FIELDS.get(name, {})
        expected = {renamed.get(field, field) for field in _fields(design, name)}
        missing = expected - _fields(live, name)
        assert not missing, (name, missing)


def test_enums_are_only_widened(app: FastAPI) -> None:
    design = _design()["components"]["schemas"]
    live = app.openapi()["components"]["schemas"]
    pairs = [
        ("Lead", "status"),
        ("Lead", "source"),
        ("LeadActivity", "kind"),
        ("SiteVisit", "status"),
        ("ConsentText", "kind"),
    ]
    for name, field in pairs:
        before = _enum(design[name]["properties"][field])
        after = _enum(live[name]["properties"][field])
        assert before <= after, (name, field, before - after)
    assert "marketing" in _enum(live["ConsentText"]["properties"]["kind"])


def test_inbox_and_export_keep_the_contract_filters(app: FastAPI) -> None:
    design = _design()["paths"]
    live = app.openapi()["paths"]
    for path in ("/api/v1/admin/leads", "/api/v1/admin/leads/export.csv"):

        def names(spec: dict[str, Any], p: str = path) -> set[str]:
            return {
                param.get("name") or param["$ref"].rsplit("/", 1)[-1]
                for param in spec[p]["get"].get("parameters", [])
            }

        assert names(design) <= names(live), path


def test_public_intake_is_public_and_rate_limited(app: FastAPI) -> None:
    paths = app.openapi()["paths"]
    for path in ("leads", "site-visits", "brochure-requests"):
        operation = paths[f"/api/v1/public/{path}"]["post"]
        assert operation["x-public"] is True and operation["security"] == []
        assert "5 per 10 minutes" in operation["x-rate-limit"]
