"""The media module keeps the design contract (handbook/api/openapi-v1.yaml, D-020): every
"Media" operation exists with the same method, path, operationId and x-permission, and the
contract's fields are all there (additions are allowed, renames are not)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI

CONTRACT = Path(__file__).resolve().parents[3] / "handbook" / "api" / "openapi-v1.yaml"
# Contract additions (Phase 4 part 4, D-035): where a library item is used.
ADDED_OPERATIONS = {("get", "/api/v1/admin/media/{id}/usage"): ("media_usage", "media.upload")}


def _media_operations(spec: dict[str, Any]) -> dict[tuple[str, str], tuple[str, str | None]]:
    found = {}
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if isinstance(operation, dict) and "Media" in operation.get("tags", []):
                found[(method, path)] = (operation["operationId"], operation.get("x-permission"))
    return found


def test_media_operations_match_the_design_contract(app: FastAPI) -> None:
    design = _media_operations(yaml.safe_load(CONTRACT.read_text()))
    assert len(design) == 10
    live = _media_operations(app.openapi())
    assert {key: value for key, value in live.items() if key not in ADDED_OPERATIONS} == design
    for key, value in ADDED_OPERATIONS.items():
        assert live[key] == value


def test_media_schemas_keep_every_contract_field(app: FastAPI) -> None:
    design = yaml.safe_load(CONTRACT.read_text())["components"]["schemas"]
    live = app.openapi()["components"]["schemas"]
    names = (
        "Media",
        "MediaUpdate",
        "MediaLinkInput",
        "MediaLinkUpdate",
        "ImageUpload",
        "UploadSignatureRequest",
        "UploadSignature",
        "UploadConfirm",
        "ReorderRequest",
    )
    for name in names:
        assert set(design[name]["properties"]) <= set(live[name]["properties"]), name
    linked = design["LinkedMedia"]["allOf"][1]["properties"]
    assert set(linked) <= set(live["LinkedMedia"]["properties"])
    image_upload = app.openapi()["paths"]["/api/v1/admin/media/images"]["post"]["requestBody"]
    assert image_upload["content"]["multipart/form-data"]["schema"]["$ref"].endswith("/ImageUpload")
