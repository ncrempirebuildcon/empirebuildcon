"""Regression tests for the Phase 4 part 5 review (review_out/phase4e-review.md; ids M1 … L11).

Each test names its finding. M1: open sign-in challenges die with the account's sessions and
with a password change. M2: the current password on /auth/password/change counts on the
lockout. M3: a rotation member who left never blocks saving lead routing. M4: only the newest
setup/reset link works. L1: forced set-up and switching admin_2fa on sign out password-only
sessions. L2: a site-visit lead's owner is told. L4: the sender name and From header. L5: no
admin reset of your own two-factor. L6: unlock and reset clear the code cap. L8: the audit log
is append-only in the database. L9: SEO defaults need settings.read too. L10: link tokens in the
fragment. L11: the GSTIN example is valid.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from conftest import GOOD_PASSWORD, SignedIn, make_user, new_client, sign_in
from empire_api.config import get_settings
from empire_api.db import get_engine, get_sessionmaker
from empire_api.mail import transport
from empire_api.platform.models import AuditLog, OutboxEvent
from empire_api.site_settings.fields import GSTIN_EXAMPLE, _gstin
from empire_api.timeutil import today_ist
from empire_api.users import lockout, service
from empire_api.users.models import User
from empire_api.users.sign_in import CHALLENGE_EXPIRED
from leads_support import enquiry, published_project, staff_client, submit_ok
from two_factor_support import TWO_FA, Clock, code, key_of, login, mail_to, turn_on, use_clock

USERS = "/api/v1/admin/users"
SETTINGS = "/api/v1/admin/settings"
NEW_PASSWORD = "a fresh long passphrase"


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    return use_clock(monkeypatch)


def flag_on_directly() -> None:
    """admin_2fa on without the route (which would also sign people out, L1)."""
    with get_sessionmaker()() as session:
        session.execute(text("UPDATE feature_flag SET enabled = true WHERE key = 'admin_2fa'"))
        session.commit()


def reset_by_email(client: TestClient, email: str, password: str = NEW_PASSWORD) -> None:
    assert client.post("/api/v1/auth/password/forgot", json={"email": email}).status_code == 204
    link = mail_to(email, "reset_link")[-1].links[0]
    token = service.token_of_link(link)
    r = client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": password})
    assert r.status_code == 204, r.text


# --- M1: challenges die with the sessions -------------------------------------------------


def test_m1_a_phished_password_can_not_finish_the_forced_setup_after_a_reset(
    app: FastAPI, owner: SignedIn, clock: Clock
) -> None:
    flag_on_directly()
    admin = make_user("admin", email="admin@example.com")
    attacker = new_client(app)
    assert login(attacker, admin.email).json()["step"] == "setup"
    reset_by_email(new_client(app), admin.email)  # the real person resets the password
    r = attacker.post(f"{TWO_FA}/enrol")
    assert r.status_code == 401 and r.json()["detail"] == CHALLENGE_EXPIRED
    assert attacker.post(f"{TWO_FA}/enrol/confirm", json={"code": "123456"}).status_code == 401


@pytest.mark.parametrize(
    "how", ["revoke_sessions", "reset_two_factor", "role_change", "deactivate"]
)
def test_m1_open_verify_challenges_die_with_the_sessions(
    app: FastAPI, owner: SignedIn, clock: Clock, how: str
) -> None:
    user = make_user("admin", email="admin@example.com")
    enrolled = turn_on(sign_in(new_client(app), user), clock)
    attacker = new_client(app)
    assert login(attacker, user.email).json()["step"] == "verify"
    h = owner.headers()
    if how == "revoke_sessions":
        assert owner.client.post(f"{USERS}/{user.id}/revoke-sessions", headers=h).status_code == 204
    elif how == "reset_two_factor":
        assert owner.client.post(f"{USERS}/{user.id}/reset-2fa", headers=h).status_code == 204
    elif how == "role_change":
        assert (
            owner.client.patch(f"{USERS}/{user.id}", json={"role": "sales"}, headers=h).status_code
            == 200
        )
    else:
        assert (
            owner.client.patch(
                f"{USERS}/{user.id}", json={"is_active": False}, headers=h
            ).status_code
            == 200
        )
        assert (
            owner.client.patch(
                f"{USERS}/{user.id}", json={"is_active": True}, headers=h
            ).status_code
            == 200
        )
    r = attacker.post(f"{TWO_FA}/verify", json={"code": code(enrolled.secret, clock)})
    assert r.status_code == 401 and r.json()["detail"] == CHALLENGE_EXPIRED


def test_m1_a_password_change_closes_open_challenges(
    app: FastAPI, owner: SignedIn, clock: Clock
) -> None:
    user = make_user("admin", email="admin@example.com")
    person = sign_in(new_client(app), user)
    enrolled = turn_on(person, clock)
    attacker = new_client(app)
    login(attacker, user.email)
    r = person.client.post(
        "/api/v1/auth/password/change",
        json={"current_password": GOOD_PASSWORD, "new_password": NEW_PASSWORD},
        headers=person.headers(),
    )
    assert r.status_code == 204
    assert (
        attacker.post(f"{TWO_FA}/verify", json={"code": code(enrolled.secret, clock)}).status_code
        == 401
    )


def test_m1_a_challenge_older_than_the_last_password_change_is_refused(
    app: FastAPI, owner: SignedIn, clock: Clock, db: Session
) -> None:
    """Belt and braces: even if a path forgot to close it, the password-change time decides."""
    user = make_user("admin", email="admin@example.com")
    enrolled = turn_on(sign_in(new_client(app), user), clock)
    attacker = new_client(app)
    login(attacker, user.email)
    db.execute(
        text("UPDATE app_user SET password_changed_at = now() + interval '1 second' WHERE id = :i"),
        {"i": user.id},
    )
    db.commit()
    assert (
        attacker.post(f"{TWO_FA}/verify", json={"code": code(enrolled.secret, clock)}).status_code
        == 401
    )
    db.execute(
        text("UPDATE app_user SET password_changed_at = now() - interval '1 hour' WHERE id = :i"),
        {"i": user.id},
    )
    db.commit()
    fresh = new_client(app)
    login(fresh, user.email)
    assert (
        fresh.post(f"{TWO_FA}/verify", json={"code": code(enrolled.secret, clock)}).status_code
        == 200
    )


# --- M2: the password-change endpoint counts -----------------------------------------------


def test_m2_wrong_current_passwords_count_and_lock(owner: SignedIn, db: Session) -> None:
    def change(current: str) -> Any:
        return owner.client.post(
            "/api/v1/auth/password/change",
            json={"current_password": current, "new_password": NEW_PASSWORD},
            headers=owner.headers(),
        )

    statuses = [change("not the password!").status_code for _ in range(6)]
    assert statuses == [400, 400, 400, 400, 400, 429]
    wrong = change("still not it!!")
    assert wrong.status_code == 429
    failed = db.scalars(
        select(AuditLog).where(AuditLog.action == "auth.password_check_failed")
    ).all()
    assert len(failed) == 5 and all(row.entity_id == str(owner.user.id) for row in failed)
    assert db.scalars(select(AuditLog).where(AuditLog.action == "user.locked")).first() is not None
    assert change(GOOD_PASSWORD).status_code == 429  # locked on this network for the window


def test_m2_a_completed_change_is_audited_and_clears_the_counter(
    owner: SignedIn, db: Session, app: FastAPI
) -> None:
    for _ in range(3):
        owner.client.post(
            "/api/v1/auth/password/change",
            json={"current_password": "wrong password!!", "new_password": NEW_PASSWORD},
            headers=owner.headers(),
        )
    ok = owner.client.post(
        "/api/v1/auth/password/change",
        json={"current_password": GOOD_PASSWORD, "new_password": NEW_PASSWORD},
        headers=owner.headers(),
    )
    assert ok.status_code == 204
    assert db.scalars(select(AuditLog).where(AuditLog.action == "user.password_changed")).one()
    fresh = new_client(app)
    for _ in range(4):
        assert (
            login(fresh, owner.user.email, "wrong password!!").status_code == 401
        )  # count restarted


# --- M3: someone who left never blocks the lead-routing group ------------------------------


def test_m3_a_deactivated_rotation_member_does_not_block_other_fields(owner: SignedIn) -> None:
    one = make_user("sales", email="s1@example.com", name="Sales 1")
    two = make_user("sales", email="s2@example.com", name="Sales 2")
    h = owner.headers()
    ids = [str(one.id), str(two.id)]
    assert (
        owner.client.patch(
            f"{SETTINGS}/lead_routing",
            json={
                "mode": "round_robin",
                "round_robin_user_ids": ids,
                "single_owner_user_id": str(two.id),
            },
            headers=h,
        ).status_code
        == 200
    )
    assert (
        owner.client.patch(f"{USERS}/{two.id}", json={"is_active": False}, headers=h).status_code
        == 200
    )
    r = owner.client.patch(
        f"{SETTINGS}/lead_routing", json={"inbox_email": "inbox@example.com"}, headers=h
    )
    assert r.status_code == 200, r.text
    rows = {row["user"]["name"]: row for row in owner.client.get(SETTINGS).json()["lead_rotation"]}
    assert rows["Sales 2"]["can_own"] is False and rows["Sales 2"]["in_rotation"] is False
    reordered = owner.client.patch(
        f"{SETTINGS}/lead_routing",
        json={"round_robin_user_ids": [str(two.id), str(one.id)]},
        headers=h,
    )
    assert reordered.status_code == 200
    removed = owner.client.patch(
        f"{SETTINGS}/lead_routing", json={"round_robin_user_ids": [str(one.id)]}, headers=h
    )
    assert removed.status_code == 200
    readded = owner.client.patch(
        f"{SETTINGS}/lead_routing",
        json={"round_robin_user_ids": [str(one.id), str(two.id)]},
        headers=h,
    )
    assert readded.status_code == 422
    assert {e["field"] for e in readded.json()["errors"]} == {"round_robin_user_ids.1"}


def test_m3_a_demoted_single_owner_blocks_only_when_chosen_again(owner: SignedIn) -> None:
    sales = make_user("sales", email="s1@example.com")
    other = make_user("sales", email="s2@example.com")
    h = owner.headers()
    assert (
        owner.client.patch(
            f"{SETTINGS}/lead_routing", json={"single_owner_user_id": str(sales.id)}, headers=h
        ).status_code
        == 200
    )
    assert (
        owner.client.patch(f"{USERS}/{sales.id}", json={"role": "marketing"}, headers=h).status_code
        == 200
    )
    assert (
        owner.client.patch(
            f"{SETTINGS}/lead_routing", json={"mode": "manual"}, headers=h
        ).status_code
        == 200
    )
    assert (
        owner.client.patch(
            f"{SETTINGS}/lead_routing", json={"single_owner_user_id": str(other.id)}, headers=h
        ).status_code
        == 200
    )
    back = owner.client.patch(
        f"{SETTINGS}/lead_routing", json={"single_owner_user_id": str(sales.id)}, headers=h
    )
    assert back.status_code == 422


# --- M4: only the newest link works --------------------------------------------------------


def _invite(owner: SignedIn, email: str = "new@example.com") -> dict[str, Any]:
    r = owner.client.post(
        USERS, json={"email": email, "name": "New Person", "role": "sales"}, headers=owner.headers()
    )
    assert r.status_code == 201
    return dict(r.json())


def _link_works(client: TestClient, link: str) -> int:
    body = {"token": service.token_of_link(link), "new_password": NEW_PASSWORD}
    return client.post("/api/v1/auth/password/reset", json=body).status_code


def test_m4_a_new_setup_link_burns_the_old_one(owner: SignedIn, client: TestClient) -> None:
    person = _invite(owner)
    first = mail_to("new@example.com", "setup_link")[0].links[0]
    assert (
        owner.client.post(f"{USERS}/{person['id']}/send-reset", headers=owner.headers()).status_code
        == 204
    )
    second = mail_to("new@example.com", "setup_link")[-1].links[0]
    assert first != second
    assert _link_works(client, first) == 400
    assert _link_works(client, second) == 204


def test_m4_an_email_change_burns_open_links(owner: SignedIn, client: TestClient) -> None:
    person = _invite(owner, "typo@exmaple.com")
    old = mail_to("typo@exmaple.com", "setup_link")[0].links[0]
    r = owner.client.patch(
        f"{USERS}/{person['id']}", json={"email": "right@example.com"}, headers=owner.headers()
    )
    assert r.status_code == 200
    assert _link_works(client, old) == 400


def test_m4_deactivate_and_reactivate_burn_open_links(owner: SignedIn, client: TestClient) -> None:
    person = _invite(owner)
    old = mail_to("new@example.com", "setup_link")[0].links[0]
    h = owner.headers()
    owner.client.patch(f"{USERS}/{person['id']}", json={"is_active": False}, headers=h)
    owner.client.patch(f"{USERS}/{person['id']}", json={"is_active": True}, headers=h)
    assert _link_works(client, old) == 400


def test_m4_a_second_reset_request_burns_the_first_link(
    owner: SignedIn, client: TestClient
) -> None:
    for _ in range(2):
        assert (
            client.post(
                "/api/v1/auth/password/forgot", json={"email": owner.user.email}
            ).status_code
            == 204
        )
    first, second = [m.links[0] for m in mail_to(owner.user.email, "reset_link")]
    assert _link_works(client, first) == 400
    assert _link_works(client, second) == 204


# --- L1: password-only sessions end ---------------------------------------------------------


def test_l1_forced_setup_signs_out_older_sessions(
    app: FastAPI, owner: SignedIn, clock: Clock
) -> None:
    admin = make_user("admin", email="admin@example.com")
    older = sign_in(new_client(app), admin)
    flag_on_directly()
    fresh = new_client(app)
    login(fresh, admin.email)
    secret = key_of(fresh.post(f"{TWO_FA}/enrol").json())
    assert (
        fresh.post(f"{TWO_FA}/enrol/confirm", json={"code": code(secret, clock)}).status_code == 200
    )
    assert older.client.get("/api/v1/auth/me").status_code == 401
    assert fresh.get("/api/v1/auth/me").status_code == 200


def test_l1_switching_the_flag_on_signs_out_admins_without_two_factor(
    app: FastAPI, owner: SignedIn, clock: Clock, db: Session
) -> None:
    turn_on(owner, clock)
    without = sign_in(new_client(app), make_user("admin", email="a1@example.com"))
    with_2fa = sign_in(new_client(app), make_user("admin", email="a2@example.com"))
    turn_on(with_2fa, clock)
    sales = staff_client(app, "sales")
    r = owner.client.patch(
        "/api/v1/admin/flags/admin_2fa", json={"enabled": True}, headers=owner.headers()
    )
    assert r.status_code == 200
    assert without.client.get("/api/v1/auth/me").status_code == 401
    for still in (owner, with_2fa, sales):
        assert still.client.get("/api/v1/auth/me").status_code == 200
    [row] = db.scalars(select(AuditLog).where(AuditLog.action == "user.sessions_revoked")).all()
    assert row.entity_id == str(without.user.id) and row.actor_user_id == owner.user.id
    assert row.changes["reason"] == [None, "admin_2fa switched on"]
    flag_row = db.scalars(select(AuditLog).where(AuditLog.action == "flag.changed")).one()
    assert flag_row.changes == {"enabled": [False, True], "accounts_signed_out": [None, 1]}
    assert login(new_client(app), without.user.email).json()["step"] == "setup"


# --- L2: a site-visit lead's owner is told --------------------------------------------------


def test_l2_the_routed_owner_of_a_site_visit_request_gets_now_yours(
    client: TestClient,
    owner: SignedIn,
    texts: dict[str, Any],
    intake_unlimited: None,
    qr_present: None,
) -> None:
    project = published_project(owner)
    sales = make_user("sales", email="sales1@example.com", name="Sales 1")
    owner.client.patch(
        f"{SETTINGS}/lead_routing",
        json={
            "mode": "round_robin",
            "round_robin_user_ids": [str(sales.id)],
            "inbox_email": "inbox@example.com",
        },
        headers=owner.headers(),
    )
    body = enquiry(texts, 1, project_slug=project["slug"], source="site_visit")
    day = today_ist() + timedelta(days=2)
    submit_ok(
        client,
        {**body, "preferred_date": day.isoformat(), "preferred_slot": "morning"},
        "site-visits",
    )
    assert [m.template for m in mail_to("sales1@example.com")] == ["lead_assigned"]
    assert [m.template for m in mail_to("inbox@example.com")] == ["visit_requested"]


# --- L4: the sender name and the From header ------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Empire: Sales",
        "Empire (CMS)",
        'Empire "x"',
        "Empire <x>",
        "A, B",
        "A; B",
        "a@b",
        "A/B",
        "Hi!",
        "A\\B",
        "A#B",
    ],
)
def test_l4_characters_that_change_the_from_header_are_refused(owner: SignedIn, name: str) -> None:
    r = owner.client.patch(f"{SETTINGS}/email", json={"sender_name": name}, headers=owner.headers())
    assert r.status_code == 422, name


@pytest.mark.parametrize(
    "name", ["Empire Sales & Co.", "O'Brien-Homes", "एम्पायर बिल्डकॉन", "Empire 2"]
)
def test_l4_ordinary_names_are_allowed(owner: SignedIn, name: str) -> None:
    r = owner.client.patch(f"{SETTINGS}/email", json={"sender_name": name}, headers=owner.headers())
    assert r.status_code == 200, r.text


def test_l4_the_from_header_is_built_with_formataddr() -> None:
    assert transport.from_header("Empire CMS") == "Empire CMS <no-reply@example.com>"
    assert transport.from_header("Empire Pvt. Ltd.") == '"Empire Pvt. Ltd." <no-reply@example.com>'
    assert transport.from_header("एम्पायर").startswith("=?utf-8?")


# --- L5: not your own two-factor through the admin route ------------------------------------


def test_l5_the_admin_route_refuses_your_own_account(
    owner: SignedIn, clock: Clock, db: Session
) -> None:
    turn_on(owner, clock)
    r = owner.client.post(f"{USERS}/{owner.user.id}/reset-2fa", headers=owner.headers())
    assert r.status_code == 409 and "My account" in r.json()["detail"]
    assert owner.client.get("/api/v1/auth/me").json()["two_factor_enabled"] is True


# --- L6: unlock and reset clear the code cap ------------------------------------------------


@pytest.mark.parametrize("how", ["unlock", "reset"])
def test_l6_unlock_and_reset_clear_the_code_cap(
    app: FastAPI, owner: SignedIn, clock: Clock, monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    monkeypatch.setattr(lockout, "CODE_LIMIT_PER_HOUR", 2)
    user = make_user("admin", email="admin@example.com")
    enrolled = turn_on(sign_in(new_client(app), user), clock)  # the confirmation is code 1
    capped = new_client(app)
    login(capped, user.email)
    assert capped.post(f"{TWO_FA}/verify", json={"code": "000000"}).status_code == 401  # code 2
    over = capped.post(f"{TWO_FA}/verify", json={"code": code(enrolled.secret, clock)})
    assert over.status_code == 429
    assert (
        over.json()["detail"] == "Too many two-factor codes were tried. Try again in about an hour."
    )
    assert 0 < int(over.headers["retry-after"]) <= 3600
    password = GOOD_PASSWORD
    if how == "unlock":
        assert (
            owner.client.post(f"{USERS}/{user.id}/unlock", headers=owner.headers()).status_code
            == 204
        )
    else:
        reset_by_email(new_client(app), user.email)
        password = NEW_PASSWORD
    again = new_client(app)
    assert login(again, user.email, password).status_code == 202
    assert (
        again.post(f"{TWO_FA}/verify", json={"code": code(enrolled.secret, clock)}).status_code
        == 200
    )


# --- L8: append-only in the database --------------------------------------------------------


def test_l8_the_database_refuses_editing_or_deleting_audit_rows(owner: SignedIn) -> None:
    for statement in ("UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log"):
        with pytest.raises(DBAPIError, match="append-only"), get_engine().begin() as conn:
            conn.execute(text(statement))
    with get_engine().begin() as conn:
        count = conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one()
        conn.execute(
            text("INSERT INTO audit_log (action, entity_type, entity_id) VALUES ('t', 't', 't')")
        )
        assert conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one() == count + 1


# --- L9: SEO defaults need settings.read as well --------------------------------------------


def test_l9_content_editors_can_not_save_seo_defaults_and_the_spec_says_so(app: FastAPI) -> None:
    editor = staff_client(app, "content_editor")
    r = editor.client.patch(
        f"{SETTINGS}/seo_defaults", json={"default_title": "x"}, headers=editor.headers()
    )
    assert r.status_code == 403
    operation = app.openapi()["paths"]["/api/v1/admin/settings/{group}"]["patch"]
    assert "settings.read" in operation["x-permission-by-group"]["seo_defaults"]
    assert "content editors" in operation["description"]


# --- L10: tokens in the fragment ------------------------------------------------------------


def test_l10_links_carry_the_token_in_the_fragment() -> None:
    setup, reset = service.setup_link("abc"), service.reset_link("def")
    assert setup.endswith("/admin/setup#token=abc") and "?" not in setup
    assert reset.endswith("/admin/reset#token=def") and "?" not in reset
    assert service.token_of_link(setup) == "abc"
    assert service.token_of_link("https://x/admin/reset?token=old") == "old"  # queued before
    assert service.token_of_link("https://x/admin/reset") == ""


def test_l10_a_link_queued_in_the_old_format_is_still_emailed(owner: SignedIn, db: Session) -> None:
    user = db.get(User, owner.user.id)
    assert user is not None
    token = service.issue_password_token(db, user, purpose="reset", actor_id=None)
    db.commit()
    old_style = (
        get_settings().fernet().encrypt(f"https://x/admin/reset?token={token}".encode()).decode()
    )
    db.execute(
        update(OutboxEvent)
        .where(OutboxEvent.type == "user.password_reset_requested")
        .values(
            payload={"user_id": str(user.id), "link_encrypted": old_style, "expires_in_minutes": 30}
        )
    )
    db.commit()
    assert len(mail_to(owner.user.email, "reset_link")) == 1


# --- L11: the GSTIN example ---------------------------------------------------------------


def test_l11_the_gstin_example_passes_its_own_check(owner: SignedIn) -> None:
    assert _gstin(GSTIN_EXAMPLE) == GSTIN_EXAMPLE
    r = owner.client.patch(f"{SETTINGS}/company", json={"gstin": "ABC"}, headers=owner.headers())
    assert GSTIN_EXAMPLE in r.json()["errors"][0]["message"]
    assert (
        owner.client.patch(
            f"{SETTINGS}/company", json={"gstin": GSTIN_EXAMPLE}, headers=owner.headers()
        ).status_code
        == 200
    )
