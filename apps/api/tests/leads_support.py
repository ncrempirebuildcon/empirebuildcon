"""Helpers for the leads module's tests: consent texts, public form bodies, a published project,
staff of each role in their own client, and reading rows back.

Fixtures (conftest.py): `texts` (the current draft consent texts), `intake_unlimited` (the
public intake allows 5 submissions per 10 minutes per IP and phone, and every TestClient call
comes from one address; tests/test_leads_intake.py tests the real limits) and `sales_pair`.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
import structlog
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import SignedIn, make_user, new_client, sign_in
from empire_api.leads.models import Lead
from projects_support import create_project, make_ready, ok, publish

PUBLIC = "/api/v1/public"
LEADS = "/api/v1/admin/leads"
VISITS = "/api/v1/admin/site-visits"


def given(text: dict[str, Any]) -> dict[str, Any]:
    return {"accepted": True, "consent_text_id": text["id"], "version": text["version"]}


def phone(n: int) -> str:
    """A different valid mobile number per test lead: 98765 0000n."""
    return f"98765 {n:05d}"


def enquiry(texts: dict[str, dict[str, Any]], n: int = 1, **fields: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": f"Visitor {n}",
        "phone": phone(n),
        "source": "contact_form",
        "page_url": "https://empirebuildcon.com/contact",
        "consent": given(texts["lead_form"]),
    }
    body.update(fields)
    return body


def submit(signed_or_client: Any, body: dict[str, Any], path: str = "leads") -> Any:
    client = getattr(signed_or_client, "client", signed_or_client)
    return client.post(f"{PUBLIC}/{path}", json=body)


def submit_ok(signed_or_client: Any, body: dict[str, Any], path: str = "leads") -> str:
    """Submit and return the new lead's reference."""
    return str(ok(submit(signed_or_client, body, path), 201)["reference"])


def published_project(owner: SignedIn, name: str = "Aurum Heights") -> dict[str, Any]:
    """A live project (needs the `qr_present` fixture for the RERA QR blocker)."""
    project = create_project(owner, name)
    make_ready(owner, project["id"])
    ok(publish(owner, project["id"]))
    return dict(project)


def staff_client(app: FastAPI, role: str, email: str | None = None, name: str = "") -> SignedIn:
    """A signed-in staff member of `role` in their own client (own cookie jar)."""
    user = make_user(
        role,
        email=email or f"{role}-{uuid.uuid4().hex[:6]}@example.com",
        name=name or role.replace("_", " ").title(),
    )
    return sign_in(new_client(app), user)


def lead_by_reference(db: Session, reference: str) -> Lead:
    db.expire_all()
    lead = db.scalar(select(Lead).where(Lead.reference == reference))
    assert lead is not None, reference
    return lead


def lead_id(db: Session, reference: str) -> str:
    return str(lead_by_reference(db, reference).id)


def assign(owner: SignedIn, lead: str, user_id: uuid.UUID | None) -> Any:
    body = {"owner_user_id": str(user_id) if user_id else None}
    return ok(owner.client.patch(f"{LEADS}/{lead}", json=body, headers=owner.headers()))


@contextmanager
def captured_logs(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[dict[str, Any]]]:
    """Every structured log line written while the block runs, as dicts.

    WHY swap the module loggers: they cache their output on first use, so a logger used by an
    earlier test would bypass `capture_logs`. Fresh ones made inside the block don't.
    """
    with structlog.testing.capture_logs() as entries:
        for name, module in list(sys.modules.items()):
            if name.startswith("empire_api") and hasattr(module, "log"):
                monkeypatch.setattr(module, "log", structlog.get_logger(name))
        yield entries
