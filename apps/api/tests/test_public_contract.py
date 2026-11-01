"""The public read-only operations keep the design contract (handbook/api/openapi-v1.yaml).

Every public operation has the contract's method, path, operationId, tags, x-public marker,
and empty security requirement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI

CONTRACT = Path(__file__).resolve().parents[3] / "handbook" / "api" / "openapi-v1.yaml"
PUBLIC_TAG = "Public"

PUBLIC_OPERATIONS = {
    ("get", "/api/v1/public/site"): "public_site",
    ("get", "/api/v1/public/projects"): "public_list_projects",
    ("get", "/api/v1/public/projects/{slug}"): "public_get_project",
    ("get", "/api/v1/public/projects/{slug}/configurations/{config_slug}"): "public_get_property",
    ("get", "/api/v1/public/properties"): "public_list_properties",
    ("get", "/api/v1/public/cities"): "public_list_cities",
    ("get", "/api/v1/public/pages/{slug}"): "public_get_page",
    ("get", "/api/v1/public/posts"): "public_list_posts",
    ("get", "/api/v1/public/posts/{slug}"): "public_get_post",
    ("get", "/api/v1/public/faqs"): "public_list_faqs",
    ("get", "/api/v1/public/testimonials"): "public_list_testimonials",
    ("get", "/api/v1/public/redirects"): "public_list_redirects",
    ("get", "/api/v1/public/sitemap"): "public_sitemap",
}


def _design() -> dict[str, Any]:
    return dict(yaml.safe_load(CONTRACT.read_text(encoding="utf-8")))


def test_public_operations_match_the_design_contract(app: FastAPI) -> None:
    spec = app.openapi()
    design = _design()

    for (method, path), expected_op_id in PUBLIC_OPERATIONS.items():
        assert path in spec["paths"], f"Missing route {path} in generated OpenAPI spec"
        assert method in spec["paths"][path], f"Missing {method.upper()} {path} in spec"
        op = spec["paths"][path][method]

        assert op["operationId"] == expected_op_id, (
            f"Operation id mismatch for {method.upper()} {path}: got {op['operationId']}, "
            f"expected {expected_op_id}"
        )
        assert PUBLIC_TAG in op.get("tags", []), f"{PUBLIC_TAG} tag missing on {path}"
        assert op.get("x-public") is True, f"x-public missing on {path}"
        assert op.get("security") == [], f"security requirement on {path} must be empty []"

        # Also confirm it exists in handbook/api/openapi-v1.yaml design contract
        assert path in design["paths"], f"Contract missing route {path}"
        assert method in design["paths"][path], f"Contract missing {method.upper()} {path}"
        design_op = design["paths"][path][method]
        assert design_op["operationId"] == expected_op_id


def test_all_13_operations_accounted_for(app: FastAPI) -> None:
    spec = app.openapi()
    public_ops = [
        (method, path)
        for path, item in spec["paths"].items()
        for method, op in item.items()
        if PUBLIC_TAG in op.get("tags", [])
    ]
    assert len(public_ops) == 13
    assert len(PUBLIC_OPERATIONS) == 13
