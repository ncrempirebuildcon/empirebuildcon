"""The content, marketing and SEO operations keep the design contract (handbook/api/
openapi-v1.yaml, D-020): same method, path, operationId and x-permission for every operation
outside Phase 5's public routes; every contract schema field is present (additions allowed,
deviations listed); enums only widened. Additions and deviations are recorded in D-035."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # PyYAML comes with uvicorn[standard]
from fastapi import FastAPI

CONTRACT = Path(__file__).resolve().parents[3] / "handbook" / "api" / "openapi-v1.yaml"
TAGS = {"Content", "Marketing", "SEO"}
# TODO(phase-5): the public content routes (pages, posts, faqs, testimonials, redirects,
# sitemap) are built with the public site.
PHASE_5 = "/api/v1/public/"
ADDED_OPERATIONS = {("put", "/api/v1/admin/faqs/order"): ("reorder_faqs", "content.write")}
# PATCH bodies and list rows are their own schemas (every field optional / no heavy fields).
SCHEMA_PAIRS = {
    "Page": "Page",
    "Post": "Post",
    "Faq": "Faq",
    "Offer": "Offer",
    "Testimonial": "Testimonial",
    "Redirect": "Redirect",
    "Seo": "Seo",
    "PageInput": "PageUpdate",
    "PostInput": "PostUpdate",
    "FaqInput": "FaqUpdate",
    "OfferInput": "OfferUpdate",
    "TestimonialInput": "TestimonialUpdate",
    "RedirectInput": "RedirectUpdate",
}
CREATE_BODIES = {
    "PageInput": "PageInput",
    "PostInput": "PostInput",
    "FaqInput": "FaqInput",
    "OfferInput": "OfferInput",
    "TestimonialInput": "TestimonialInput",
    "RedirectInput": "RedirectInput",
}


def _design() -> dict[str, Any]:
    return dict(yaml.safe_load(CONTRACT.read_text()))


def _operations(spec: dict[str, Any]) -> dict[tuple[str, str], tuple[str, str | None]]:
    found = {}
    for path, item in spec["paths"].items():
        if path.startswith(PHASE_5):
            continue
        for method, operation in item.items():
            if isinstance(operation, dict) and TAGS & set(operation.get("tags", [])):
                found[(method, path)] = (operation["operationId"], operation.get("x-permission"))
    return found


def _fields(schemas: dict[str, Any], name: str) -> set[str]:
    return set(schemas[name].get("properties", {}))


def test_operations_match_the_design_contract(app: FastAPI) -> None:
    design = _operations(_design())
    live = _operations(app.openapi())
    assert len(design) == 31  # pages 8, posts 7, FAQs 4, testimonials 4, offers 4, redirects 4
    assert {key: value for key, value in live.items() if key not in ADDED_OPERATIONS} == design
    for key, value in ADDED_OPERATIONS.items():
        assert live[key] == value


def test_every_contract_field_is_kept(app: FastAPI) -> None:
    design = _design()["components"]["schemas"]
    live = app.openapi()["components"]["schemas"]
    for contract_name, live_name in {**SCHEMA_PAIRS, **CREATE_BODIES}.items():
        missing = _fields(design, contract_name) - _fields(live, live_name)
        assert not missing, (contract_name, live_name, missing)
    # List rows keep every field of the contract's item except the heavy ones (D-035).
    assert _fields(design, "Page") - _fields(live, "PageSummary") == {
        "blocks",
        "seo",
        "translations",
    }
    assert _fields(design, "Post") - _fields(live, "PostSummary") == {"body", "seo", "translations"}


def test_blocks_are_unions_with_the_contract_fields(app: FastAPI) -> None:
    """Deviation (D-035): Block and BlockInput are discriminated unions on `type`."""
    design = _design()["components"]["schemas"]
    live = app.openapi()["components"]["schemas"]
    types = set(design["Block"]["properties"]["type"]["enum"])
    for union, base_fields in (("Block", "Block"), ("BlockInput", "BlockInput")):
        variants = [ref["$ref"].rsplit("/", 1)[-1] for ref in live[union]["oneOf"]]
        assert live[union]["discriminator"]["propertyName"] == "type"
        assert len(variants) == len(types) == 17
        seen = set()
        for variant in variants:
            assert _fields(design, base_fields) <= _fields(live, variant), variant
            seen.add(live[variant]["properties"]["type"]["const"])
        assert seen == types


def test_enums_are_only_widened(app: FastAPI) -> None:
    design = _design()["components"]["schemas"]
    live = app.openapi()["components"]["schemas"]

    def enum(schema: dict[str, Any]) -> set[str]:
        if "enum" in schema:
            return set(schema["enum"])
        for option in schema.get("anyOf", []):
            if "enum" in option:
                return set(option["enum"])
        return set()

    for name, field in (
        ("Page", "kind"),
        ("Page", "publish_state"),
        ("Post", "publish_state"),
        ("Offer", "placement"),
        ("Redirect", "status_code"),
    ):
        assert enum(design[name]["properties"][field]) <= enum(live[name]["properties"][field])


def test_no_countdown_field_exists_anywhere(app: FastAPI) -> None:
    """COMPLIANCE (AGENTS.md "No fake urgency")."""
    schemas = app.openapi()["components"]["schemas"]
    for schema in schemas.values():
        for field in schema.get("properties", {}):
            assert "countdown" not in field and "timer" not in field
