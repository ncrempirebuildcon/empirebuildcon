"""The projects module keeps the design contract (handbook/api/openapi-v1.yaml, D-020):
every "Projects" and "Catalogue" operation exists with the same method, path, operationId and
x-permission, and the shared shapes keep one schema name for requests and responses."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # PyYAML comes with uvicorn[standard]
from fastapi import FastAPI

CONTRACT = Path(__file__).resolve().parents[3] / "handbook" / "api" / "openapi-v1.yaml"
TAGS = {"Projects", "Catalogue"}


def _operations(spec: dict[str, Any]) -> dict[tuple[str, str], tuple[str, str | None]]:
    found = {}
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if isinstance(operation, dict) and TAGS & set(operation.get("tags", [])):
                found[(method, path)] = (operation["operationId"], operation.get("x-permission"))
    return found


def test_projects_and_catalogue_match_the_design_contract(app: FastAPI) -> None:
    design = _operations(yaml.safe_load(CONTRACT.read_text()))
    live = _operations(app.openapi())
    assert len(design) == 52
    assert live == design


def test_shared_shapes_keep_one_schema_name(app: FastAPI) -> None:
    """WHY: Area, Price, … serve requests and responses; if their schemas differed, FastAPI would
    publish `Area-Input` and `Area-Output` and the web client's type names would change."""
    names = set(app.openapi()["components"]["schemas"])
    assert not [n for n in names if n.endswith(("-Input", "-Output"))]
    shared = {"Area", "Price", "Seo", "Translations", "ReraAccount", "PaymentPlanStage"}
    assert shared <= names
    contract = set(yaml.safe_load(CONTRACT.read_text())["components"]["schemas"])
    # ProjectSummary and ProjectDetail arrive with the public endpoints (Phase 5); the CMS list
    # uses ProjectAdminSummary, which has every ProjectSummary field (test below).
    used = {
        "ProjectAdmin",
        "ProjectInput",
        "Location",
        "LocationInput",
        "CityRef",
        "LocalityRef",
        "Rera",
        "Media",
        "LinkedMedia",
        "Faq",
        "City",
        "CityInput",
        "Locality",
        "LocalityInput",
        "Amenity",
        "AmenityInput",
        "Tower",
        "TowerInput",
        "Configuration",
        "ConfigurationInput",
        "Specification",
        "SpecificationInput",
        "LocationAdvantage",
        "LocationAdvantageInput",
        "ConstructionUpdate",
        "ConstructionUpdateInput",
        "PaymentPlan",
        "PaymentPlanInput",
        "ReorderRequest",
        "MapsResolveRequest",
        "MapsResolveResult",
    }
    assert used <= contract
    assert used <= names


def test_project_admin_keeps_every_contract_field(app: FastAPI) -> None:
    design = yaml.safe_load(CONTRACT.read_text())["components"]["schemas"]

    def fields(name: str) -> set[str]:
        schema = design[name]
        found = set(schema.get("properties", {}))
        for part in schema.get("allOf", []):
            found |= (
                fields(part["$ref"].rsplit("/", 1)[-1])
                if "$ref" in part
                else set(part.get("properties", {}))
            )
        return found

    live = app.openapi()["components"]["schemas"]
    assert fields("ProjectAdmin") <= set(live["ProjectAdmin"]["properties"])
    assert fields("ProjectSummary") <= set(live["ProjectAdminSummary"]["properties"])
    assert fields("ProjectInput") <= set(live["ProjectUpdate"]["properties"])
