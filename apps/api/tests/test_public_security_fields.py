"""Public schemas and responses never expose staff, internal, or personal fields (Scope #12).

INVARIANT: No staff or personal fields (created_by, updated_by, internal notes, passwords,
personal contact records, staff user ids) may ever be present in any public schema or answer.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.orm import Session

from empire_api.content.models import Faq, Page, Post
from empire_api.content.models import Testimonial as DbTestimonial
from empire_api.projects.models import City, Configuration, Project
from empire_api.public import schemas
from empire_api.seo.models import Redirect

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
        "consent_date",  # S12: dropped from public testimonials
        "source_url",  # S12: dropped from public testimonials
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


def test_real_endpoint_responses_have_no_forbidden_fields(db: Session, client: TestClient) -> None:
    """S16: Validate actual JSON responses from real public endpoints with seeded database."""
    # Seed live entities across all public content types
    city = City(name="Probe City", slug="probe-city-secure", state="UP")
    db.add(city)
    db.flush()

    p = Project(
        name="Probe Project",
        slug="probe-project-secure",
        status="ongoing",
        sales_status="available",
        publish_state="published",
        city_id=city.id,
    )
    db.add(p)
    db.flush()

    cfg = Configuration(
        project_id=p.id,
        name="Probe Config",
        slug="probe-cfg-secure",
        property_type="apartment",
        sales_status="available",
        price_min_inr=1_000_000,
        price_max_inr=2_000_000,
        area_min_sqm=Decimal("50.0"),
        area_max_sqm=Decimal("60.0"),
        sort_order=1,
    )
    db.add(cfg)

    faq = Faq(question="Security FAQ?", answer="Safe answer.", sort_order=1, is_visible=True)
    db.add(faq)

    testimonial = DbTestimonial(
        person_name="Secure User",
        quote="Clean experience.",
        source="google",
        consent_date=datetime.now(UTC),
        is_visible=True,
    )
    db.add(testimonial)

    post = Post(
        title="Secure Post",
        slug="probe-post-secure",
        body="Post body text.",
        publish_state="published",
    )
    db.add(post)

    page = Page(
        title="Secure Page",
        slug="probe-page-secure",
        kind="standard",
        publish_state="published",
    )
    db.add(page)

    redirect = Redirect(
        from_path="/old-secure-probe",
        to_path="/new-secure-probe",
        status_code=308,
        is_active=True,
    )
    db.add(redirect)
    db.commit()

    def _check_payload(val: Any, path: str = "") -> None:
        if isinstance(val, dict):
            for k, v in val.items():
                cur_path = f"{path}.{k}" if path else k
                assert k not in FORBIDDEN_FIELD_NAMES, (
                    f"Real response at {cur_path} contains forbidden field: {k}"
                )
                _check_payload(v, cur_path)
        elif isinstance(val, list):
            for idx, item in enumerate(val):
                _check_payload(item, f"{path}[{idx}]")

    endpoints_to_probe = [
        "/api/v1/public/site",
        "/api/v1/public/projects",
        f"/api/v1/public/projects/{p.slug}",
        "/api/v1/public/properties",
        f"/api/v1/public/projects/{p.slug}/configurations/{cfg.slug}",
        "/api/v1/public/cities",
        "/api/v1/public/faqs",
        "/api/v1/public/testimonials",
        "/api/v1/public/posts",
        f"/api/v1/public/posts/{post.slug}",
        f"/api/v1/public/pages/{page.slug}",
        "/api/v1/public/redirects",
        "/api/v1/public/sitemap",
    ]

    for ep in endpoints_to_probe:
        res = client.get(ep)
        assert res.status_code == 200, f"Endpoint {ep} failed with status {res.status_code}"
        payload = res.json()
        _check_payload(payload, ep)

        # S2: Redirects must never expose an "id" field and must return populated items
        if ep.endswith("/redirects"):
            assert len(payload) >= 1, "Redirects list must contain seeded items"
            for redirect_item in payload:
                assert "id" not in redirect_item
