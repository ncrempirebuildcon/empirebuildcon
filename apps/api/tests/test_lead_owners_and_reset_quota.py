"""Part 5 review fixes:

1. An account that has never set a password (invited) can't be given leads: not by round robin
   (listed or by default), not as the single owner, not in GET /admin/lead-owners, and not by
   manual assignment (422 with its own message). Settings refuse it in the rotation and as the
   single owner. Deactivated accounts are refused everywhere too.
2. Password-reset requests are capped at 5 per email address per UTC day, on top of 3 an hour,
   with the same answers for real and unknown emails.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from conftest import SignedIn, make_user
from empire_api.leads.routing import OWNER_INVALID, OWNER_NOT_SET_UP
from empire_api.platform import rate_limit
from empire_api.site_settings.models import Setting
from empire_api.users import passwords
from empire_api.users.models import User
from leads_support import LEADS, enquiry, lead_by_reference, lead_id, submit_ok
from two_factor_support import mail_to

SETTINGS = "/api/v1/admin/settings"


@pytest.fixture
def people() -> dict[str, Any]:
    return {
        "ready": make_user("sales", email="ready@example.com", name="Ready"),
        "invited": make_user("sales", email="invited@example.com", name="Invited", password=None),
        "gone": make_user("sales", email="gone@example.com", name="Gone", is_active=False),
    }


def routing(db: Session, **config: Any) -> None:
    """Store lead_routing directly (as an older row might hold it), skipping the Settings checks."""
    db.merge(Setting(key="lead_routing", value={"mode": "round_robin", **config}))
    db.commit()


# --- 1. Invited accounts and leads ---------------------------------------------------------


def test_lead_owners_lists_only_people_who_can_sign_in(
    owner: SignedIn, people: dict[str, Any]
) -> None:
    names = {o["name"] for o in owner.client.get("/api/v1/admin/lead-owners").json()}
    assert "Ready" in names
    assert "Invited" not in names and "Gone" not in names


def test_round_robin_by_default_skips_invited_and_deactivated_sales(
    client: TestClient, owner: SignedIn, people: dict[str, Any], texts: dict[str, Any],
    intake_unlimited: None, db: Session,
) -> None:  # fmt: skip
    routing(db, round_robin_user_ids=[])
    owners = {
        lead_by_reference(db, submit_ok(client, enquiry(texts, n))).owner_user_id for n in (1, 2, 3)
    }
    assert owners == {people["ready"].id}


def test_a_listed_invited_account_is_skipped_by_round_robin(
    client: TestClient, owner: SignedIn, people: dict[str, Any], texts: dict[str, Any],
    intake_unlimited: None, db: Session,
) -> None:  # fmt: skip
    ids = [str(people["invited"].id), str(people["ready"].id), str(people["gone"].id)]
    routing(db, round_robin_user_ids=ids)
    owners = {
        lead_by_reference(db, submit_ok(client, enquiry(texts, n))).owner_user_id for n in (1, 2)
    }
    assert owners == {people["ready"].id}
    rows = {r["user"]["name"]: r for r in owner.client.get(SETTINGS).json()["lead_rotation"]}
    assert rows["Invited"]["can_own"] is False and rows["Invited"]["in_rotation"] is False
    assert rows["Ready"]["gets_next"] is True


def test_an_invited_single_owner_leaves_the_lead_in_the_inbox(
    client: TestClient, owner: SignedIn, people: dict[str, Any], texts: dict[str, Any],
    intake_unlimited: None, db: Session,
) -> None:  # fmt: skip
    db.merge(
        Setting(
            key="lead_routing",
            value={"mode": "single", "single_owner_user_id": str(people["invited"].id)},
        )
    )
    db.commit()
    assert lead_by_reference(db, submit_ok(client, enquiry(texts, 1))).owner_user_id is None


def test_a_duplicate_of_an_invited_owners_lead_is_routed_afresh(
    client: TestClient, owner: SignedIn, people: dict[str, Any], texts: dict[str, Any],
    intake_unlimited: None, db: Session,
) -> None:  # fmt: skip
    first = lead_by_reference(db, submit_ok(client, enquiry(texts, 1)))
    first.owner_user_id = people["invited"].id  # e.g. given to them before this rule existed
    db.commit()
    routing(db, round_robin_user_ids=[str(people["ready"].id)])
    again = lead_by_reference(db, submit_ok(client, enquiry(texts, 1)))
    assert again.duplicate_of_id == first.id and again.owner_user_id == people["ready"].id


def test_settings_refuse_invited_and_deactivated_people(
    owner: SignedIn, people: dict[str, Any]
) -> None:
    ids = [str(people["ready"].id), str(people["invited"].id), str(people["gone"].id)]
    r = owner.client.patch(
        f"{SETTINGS}/lead_routing",
        json={
            "mode": "round_robin",
            "round_robin_user_ids": ids,
            "single_owner_user_id": str(people["invited"].id),
        },
        headers=owner.headers(),
    )
    assert r.status_code == 422
    errors = {e["field"]: e["message"] for e in r.json()["errors"]}
    assert errors["round_robin_user_ids.1"] == OWNER_NOT_SET_UP
    assert errors["single_owner_user_id"] == OWNER_NOT_SET_UP
    assert "round_robin_user_ids.0" not in errors
    assert "active" in errors["round_robin_user_ids.2"]


@pytest.mark.parametrize(
    ("who", "message"), [("invited", OWNER_NOT_SET_UP), ("gone", OWNER_INVALID)]
)
def test_manual_assignment_refuses_them(
    client: TestClient, owner: SignedIn, people: dict[str, Any], texts: dict[str, Any],
    intake_unlimited: None, db: Session, who: str, message: str,
) -> None:  # fmt: skip
    lead = lead_id(db, submit_ok(client, enquiry(texts, 1)))
    r = owner.client.patch(
        f"{LEADS}/{lead}", json={"owner_user_id": str(people[who].id)}, headers=owner.headers()
    )
    assert r.status_code == 422
    assert r.json()["errors"] == [{"field": "owner_user_id", "message": message}]
    ok = owner.client.patch(
        f"{LEADS}/{lead}", json={"owner_user_id": str(people["ready"].id)}, headers=owner.headers()
    )
    assert ok.status_code == 200


@pytest.mark.parametrize(
    ("who", "message"), [("invited", OWNER_NOT_SET_UP), ("gone", OWNER_INVALID)]
)
def test_a_manual_lead_can_not_be_given_to_them(
    owner: SignedIn, people: dict[str, Any], who: str, message: str
) -> None:
    body = {
        "name": "Walk In",
        "phone": "98765 22222",
        "source": "phone",
        "consent_note": "Agreed on the phone to be called back about the project.",
        "owner_user_id": str(people[who].id),
    }
    r = owner.client.post(LEADS, json=body, headers=owner.headers())
    assert r.status_code == 422
    assert r.json()["errors"] == [{"field": "owner_user_id", "message": message}]


def test_once_they_set_a_password_they_can_be_given_leads(
    client: TestClient, owner: SignedIn, people: dict[str, Any], texts: dict[str, Any],
    intake_unlimited: None, db: Session,
) -> None:  # fmt: skip
    row = db.get(User, people["invited"].id)
    assert row is not None
    row.password_hash = passwords.hash_password("their own long passphrase")
    db.commit()
    names = {o["name"] for o in owner.client.get("/api/v1/admin/lead-owners").json()}
    assert "Invited" in names
    lead = lead_id(db, submit_ok(client, enquiry(texts, 1)))
    r = owner.client.patch(
        f"{LEADS}/{lead}", json={"owner_user_id": str(row.id)}, headers=owner.headers()
    )
    assert r.status_code == 200


# --- 2. Reset-email quota ------------------------------------------------------------------


class FrozenClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def forgot(client: TestClient, email: str) -> Any:
    return client.post("/api/v1/auth/password/forgot", json={"email": email})


def test_five_reset_requests_per_email_per_utc_day(
    client: TestClient, owner: SignedIn, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FrozenClock(datetime(2026, 10, 26, 1, 10, tzinfo=UTC))
    monkeypatch.setattr(rate_limit, "utcnow", clock)

    def round_of(email: str, count: int) -> list[int]:
        return [forgot(client, email).status_code for _ in range(count)]

    for email in (owner.user.email, "nobody@example.com"):
        clock.now = datetime(2026, 10, 26, 1, 10, tzinfo=UTC)
        assert round_of(email, 4) == [204, 204, 204, 429]  # 3 an hour
        clock.now = datetime(2026, 10, 26, 3, 10, tzinfo=UTC)
        statuses = round_of(email, 3)
        assert statuses == [204, 204, 429]  # 5 that UTC day
        clock.now = datetime(2026, 10, 26, 5, 10, tzinfo=UTC)
        refused = forgot(client, email)
        assert refused.status_code == 429
        assert (
            refused.json()["detail"]
            == "Too many reset requests for this email today. Try again tomorrow."
        )
        midnight = datetime(2026, 10, 27, tzinfo=UTC)
        assert int(refused.headers["retry-after"]) == int((midnight - clock.now).total_seconds())
        clock.now = midnight + timedelta(minutes=1)
        assert forgot(client, email).status_code == 204  # a new UTC day
    assert len(mail_to(owner.user.email, "reset_link")) == 6  # 5 on the first day, 1 the next


def test_the_daily_cap_answers_alike_for_real_and_unknown_emails(
    client: TestClient, owner: SignedIn, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FrozenClock(datetime(2026, 10, 26, 6, 0, tzinfo=UTC))
    monkeypatch.setattr(rate_limit, "utcnow", clock)
    answers: dict[str, list[tuple[int, str]]] = {}
    for email in (owner.user.email, "nobody@example.com"):
        seen = []
        for hour in (6, 8, 10):
            clock.now = datetime(2026, 10, 26, hour, 0, tzinfo=UTC)
            for _ in range(2):
                r = forgot(client, email)
                seen.append((r.status_code, r.text if r.status_code != 204 else ""))
        answers[email] = seen
    assert answers[owner.user.email] == answers["nobody@example.com"]
    assert [s for s, _ in answers[owner.user.email]] == [204, 204, 204, 204, 204, 429]
