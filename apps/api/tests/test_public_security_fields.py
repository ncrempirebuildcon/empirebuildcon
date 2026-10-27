"""Public schemas and responses never expose staff, internal, or personal fields (Scope #12).

INVARIANT: No staff or personal fields (created_by, updated_by, internal notes, passwords,
personal contact records, staff user ids) may ever be present in any public schema or answer.
"""

from __future__ import annotations

import inspect
from typing import Any

from pydantic import BaseModel

from empire_api.public import schemas

FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "created_by",
        "updated_by",
        "published_by",
        "created_by_name",
        "updated_by_name",
        "published_by_name",
        "internal_note",
        "internal_notes",
        "notes",
        "password",
        "hash",
        "hashed_password",
        "password_hash",
        "auth_token",
        "session_id",
        "edge_key",
        "secret",
        "secret_key",
        "user_id",
        "staff_id",
    }
)


def _collect_field_names(model: type[BaseModel]) -> set[str]:
    names = set(model.model_fields.keys())
    for field_info in model.model_fields.values():
        annotation = field_info.annotation
        # Check nested models
        if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
            names |= _collect_field_names(annotation)
        # Check args for generics like list[Model] or dict[str, Model]
        for arg in getattr(annotation, "__args__", ()):
            if inspect.isclass(arg) and issubclass(arg, BaseModel):
                names |= _collect_field_names(arg)
    return names


def test_public_schemas_contain_no_forbidden_fields() -> None:
    checked_models = 0
    for name, obj in inspect.getmembers(schemas):
        if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj is not BaseModel:
            fields = _collect_field_names(obj)
            forbidden = fields & FORBIDDEN_FIELD_NAMES
            assert not forbidden, (
                f"Public schema {name} contains forbidden internal/staff fields: "
                f"{sorted(forbidden)}"
            )
            checked_models += 1
    assert checked_models >= 10


def test_json_payloads_have_no_forbidden_fields() -> None:
    def _check_payload(val: Any) -> None:
        if isinstance(val, dict):
            for k, v in val.items():
                assert k not in FORBIDDEN_FIELD_NAMES, f"Payload contains forbidden field: {k}"
                _check_payload(v)
        elif isinstance(val, list):
            for item in val:
                _check_payload(item)

    # Test dummy instances of schemas
    company = schemas.PublicCompany(name="Test Co")
    regulator = schemas.PublicRegulator()
    site = schemas.PublicSite(company=company, regulator=regulator)
    _check_payload(site.model_dump())
