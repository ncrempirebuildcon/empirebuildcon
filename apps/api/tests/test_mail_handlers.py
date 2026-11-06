"""The email handlers (mail/handlers.py): password links, security notices, lead and visit alerts.

Each test sends through the real outbox and the dev transport and reads the dev mailbox
(two_factor_support.mail_to). Guards: `alert: false` sends nothing, no full phone (or email or
message) in any lead email, links never logged, a retried event never sends twice, dead links and
inactive accounts get nothing, and emails that couldn't be sent show on the dashboard."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from conftest import GOOD_PASSWORD, SignedIn, make_user, new_client, sign_in
from empire_api.db import get_sessionmaker
from empire_api.integrations.handlers import handlers_for
from empire_api.integrations.outbox_drain import drain
from empire_api.mail import handlers as mail_handlers
from empire_api.mail.events import EMAIL_EVENT_TYPES
from empire_api.mail.models import EmailMessage
from empire_api.platform.models import OutboxEvent
from empire_api.timeutil import today_ist
from empire_api.users import service as user_service
from empire_api.users.models import PasswordResetToken, User
from leads_support import (
    LEADS,
    captured_logs,
    enquiry,
    lead_id,
    published_project,
    staff_client,
    submit_ok,
)
from two_factor_support import TWO_FA, all_mail, code, login, mail_to, turn_on, use_clock

SETTINGS = "/api/v1/admin/settings"


def set_inbox(owner: SignedIn, email: str | None) -> None:
    r = owner.client.patch(
        f"{SETTINGS}/lead_routing", json={"inbox_email": email}, headers=owner.headers()
    )
    assert r.status_code == 200, r.text


def test_every_email_event_has_its_handler() -> None:
    registered = {
        event_type
        for event_type in EMAIL_EVENT_TYPES
        if any(h.__module__ == mail_handlers.__name__ for h in handlers_for(event_type))
    }
    assert registered == set(EMAIL_EVENT_TYPES)


# --- Super-admin changes (L2 security review) ------------------------------------------------


def test_a_new_super_admin_is_announced_to_every_super_admin(owner: SignedIn) -> None:
    make_user("super_admin", email="second-owner@example.com")
    r = owner.client.post(
        "/api/v1/admin/users",
        json={"email": "intruder@example.com", "name": "Intruder", "role": "super_admin"},
        headers=owner.headers(),
    )
    assert r.status_code == 201, r.text
    for to in (owner.user.email, "second-owner@example.com"):
        [notice] = mail_to(to, "admin_change")
        assert notice.subject == "A new super-admin account was created"
        assert "intruder@example.com" in notice.text
    # The new account gets its setup link only, not the notice addressed to the team.
    assert [m.template for m in mail_to("intruder@example.com")] == ["setup_link"]


def test_other_roles_and_other_edits_send_no_admin_notice(owner: SignedIn) -> None:
    r = owner.client.post(
        "/api/v1/admin/users",
        json={"email": "sales2@example.com", "name": "Sales Two", "role": "sales"},
        headers=owner.headers(),
    )
    assert r.status_code == 201
    user_id = r.json()["id"]
    renamed = owner.client.patch(
        f"/api/v1/admin/users/{user_id}", json={"name": "Sales 2"}, headers=owner.headers()
    )
    assert renamed.status_code == 200
    assert mail_to(owner.user.email, "admin_change") == []


def test_promotion_and_a_super_admin_email_change_are_announced(owner: SignedIn) -> None:
    staff = make_user("admin", email="staff@example.com")
    promoted = owner.client.patch(
        f"/api/v1/admin/users/{staff.id}", json={"role": "super_admin"}, headers=owner.headers()
    )
    assert promoted.status_code == 200, promoted.text
    [notice] = mail_to(owner.user.email, "admin_change")
    assert notice.subject == "A staff member was made a super-admin"
    moved = owner.client.patch(
        f"/api/v1/admin/users/{staff.id}",
        json={"email": "elsewhere@example.com"},
        headers=owner.headers(),
    )
    assert moved.status_code == 200, moved.text
    # The old address hears about it too, so a hijacked account can't move quietly.
    [old] = mail_to("staff@example.com", "admin_change")
    assert old.subject == "A super-admin's email address was changed"
    assert "elsewhere@example.com" in old.text
    assert mail_to("elsewhere@example.com", "admin_change") == []


def test_promotion_with_a_new_email_in_one_edit_tells_the_old_address(owner: SignedIn) -> None:
    staff = make_user("admin", email="quiet@example.com")
    r = owner.client.patch(
        f"/api/v1/admin/users/{staff.id}",
        json={"role": "super_admin", "email": "attacker@example.com"},
        headers=owner.headers(),
    )
    assert r.status_code == 200, r.text
    [old] = mail_to("quiet@example.com", "admin_change")
    assert old.subject == "A staff member was made a super-admin"
    assert "and its email address was changed" in old.text
    assert mail_to(owner.user.email, "admin_change") != []


# --- Password links ------------------------------------------------------------------------


def test_an_invite_emails_the_setup_link_and_never_logs_it(
    owner: SignedIn, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    with captured_logs(monkeypatch) as logs:
        r = owner.client.post(
            "/api/v1/admin/users",
            json={"email": "New@Example.com", "name": "New Person", "role": "sales"},
            headers=owner.headers(),
        )
    assert r.status_code == 201
    assert "token" not in r.text and "setup" not in r.text.lower().replace("invite_sent_at", "")
    [mail] = mail_to("new@example.com")
    assert mail.template == "setup_link" and mail.subject == "Set up your Empire CMS account"
    link = mail.links[0]
    assert "/admin/setup#token=" in link and "Hello New Person" in mail.text
    assert link not in repr(logs)
    payloads = repr(db.scalars(select(OutboxEvent.payload)).all())
    assert link not in payloads and link.split("token=")[1] not in payloads
    # user.created sends no second email (the setup email says an account was made)
    assert len(mail_to("new@example.com")) == 1


def test_forgot_password_emails_a_reset_link_only_for_real_accounts(
    client: Any, owner: SignedIn
) -> None:
    assert (
        client.post("/api/v1/auth/password/forgot", json={"email": owner.user.email}).status_code
        == 204
    )
    assert (
        client.post(
            "/api/v1/auth/password/forgot", json={"email": "nobody@example.com"}
        ).status_code
        == 204
    )
    [mail] = mail_to(owner.user.email, "reset_link")
    assert "/admin/reset#token=" in mail.links[0] and "30 minutes" in mail.text
    assert mail_to("nobody@example.com") == []


def test_a_link_used_or_burned_before_sending_is_not_emailed(owner: SignedIn, db: Session) -> None:
    user = db.get(User, owner.user.id)
    assert user is not None
    token = user_service.issue_password_token(db, user, purpose="reset", actor_id=None)
    db.commit()
    user_service.reset_password(
        db, token, "a brand new long passphrase", user_service.RequestMeta(ip="127.0.0.1")
    )
    assert mail_to(owner.user.email, "reset_link") == []
    assert db.scalars(
        select(OutboxEvent.status).where(OutboxEvent.type == "user.password_reset_requested")
    ).all() == ["delivered"]


def test_inactive_accounts_get_no_link(owner: SignedIn, db: Session) -> None:
    user = make_user("sales", email="gone@example.com", is_active=False)
    with get_sessionmaker()() as session:
        row = session.get(User, user.id)
        assert row is not None
        user_service.issue_password_token(session, row, purpose="reset", actor_id=None)
        session.commit()
    assert mail_to("gone@example.com") == []


def test_an_unreadable_link_is_a_permanent_failure(owner: SignedIn, db: Session) -> None:
    user = db.get(User, owner.user.id)
    assert user is not None
    user_service.issue_password_token(db, user, purpose="reset", actor_id=None)
    db.commit()
    db.execute(
        update(OutboxEvent)
        .where(OutboxEvent.type == "user.password_reset_requested")
        .values(payload={"user_id": str(user.id), "link_encrypted": "not-fernet"})
    )
    db.commit()
    drain()
    db.expire_all()
    row = db.scalars(
        select(OutboxEvent).where(OutboxEvent.type == "user.password_reset_requested")
    ).one()
    assert row.status == "dead" and row.attempts == 1
    assert "can't be read" in (row.last_error or "")


# --- Security notices ----------------------------------------------------------------------


def test_a_lock_sends_one_notice_an_hour(app: FastAPI, owner: SignedIn, db: Session) -> None:
    victim = make_user("sales", email="sales@example.com")
    stranger = new_client(app)
    for _ in range(5):
        login(stranger, victim.email, "wrong password!!")
    [notice] = mail_to(victim.email, "account_locked")
    assert "5 times" in notice.text and "contact the super-admin" in notice.text
    db.execute(text("DELETE FROM rate_limit_bucket"))
    db.commit()
    for _ in range(5):
        login(stranger, victim.email, "wrong password!!")
    assert len(mail_to(victim.email, "account_locked")) == 1
    assert db.scalars(
        select(OutboxEvent.status).where(OutboxEvent.type == "user.locked")
    ).all() == ["delivered", "delivered"]


def test_password_changes_and_resets_send_a_notice_but_the_first_password_does_not(
    owner: SignedIn, client: Any, db: Session
) -> None:
    r = owner.client.post(
        "/api/v1/auth/password/change",
        json={"current_password": GOOD_PASSWORD, "new_password": "another long passphrase"},
        headers=owner.headers(),
    )
    assert r.status_code == 204
    [changed] = mail_to(owner.user.email, "password_changed")
    assert changed.subject == "Your Empire CMS password was changed"
    invited = owner.client.post(
        "/api/v1/admin/users",
        json={"email": "fresh@example.com", "name": "Fresh", "role": "sales"},
        headers=owner.headers(),
    )
    assert invited.status_code == 201
    link = mail_to("fresh@example.com", "setup_link")[0].links[0]
    token = link.split("token=")[1]
    assert (
        client.post(
            "/api/v1/auth/password/reset",
            json={"token": token, "new_password": "my own long passphrase"},
        ).status_code
        == 204
    )
    assert mail_to("fresh@example.com", "password_changed") == []


def test_two_factor_changes_send_notices(
    app: FastAPI, owner: SignedIn, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = use_clock(monkeypatch)
    admin_user = make_user("admin", email="admin@example.com")
    admin = sign_in(new_client(app), admin_user)
    enrolled = turn_on(admin, clock)
    fresh = new_client(app)
    login(fresh, admin_user.email)
    assert (
        fresh.post(
            f"{TWO_FA}/verify", json={"recovery_code": enrolled.recovery_codes[0]}
        ).status_code
        == 200
    )
    owner.client.post(f"/api/v1/admin/users/{admin_user.id}/reset-2fa", headers=owner.headers())
    templates = [m.template for m in mail_to(admin_user.email)]
    assert set(templates) == {
        "two_factor_enabled",
        "two_factor_recovery_code_used",
        "two_factor_reset",
    }
    [used] = mail_to(admin_user.email, "two_factor_recovery_code_used")
    assert "9 are left" in used.text
    signed = sign_in(new_client(app), admin_user)
    again = turn_on(signed, clock)
    signed.client.post(
        f"{TWO_FA}/disable",
        json={"current_password": GOOD_PASSWORD, "code": code(again.secret, clock)},
        headers=signed.headers(),
    )
    assert len(mail_to(admin_user.email, "two_factor_disabled")) == 1


# --- Lead alerts ---------------------------------------------------------------------------


@pytest.fixture
def project(owner: SignedIn, qr_present: None) -> dict[str, Any]:
    return published_project(owner)


def test_a_new_lead_is_announced_to_the_sales_inbox_without_the_full_phone(
    client: Any, owner: SignedIn, texts: dict[str, Any], intake_unlimited: None, db: Session
) -> None:
    set_inbox(owner, "sales-inbox@example.com")
    body = enquiry(
        texts,
        7,
        name="Rohit Verma",
        email="rohit.private@example.org",
        message="Call after 6pm please",
    )
    reference = submit_ok(client, body)
    [mail] = mail_to("sales-inbox@example.com", "lead_alert")
    assert mail.subject == f"New lead {reference}"
    assert "Rohit" not in mail.subject
    assert "Rohit Verma" in mail.text and "+91 98xxxxxx07" in mail.text
    assert f"/admin/leads/{lead_id(db, reference)}" in mail.links[0]
    stored = all_mail()[-1]
    for secret in ("9876500007", "98765 00007", "+919876500007", "rohit.private", "after 6pm"):
        assert secret not in stored["text"] and secret not in stored["html"]
        assert secret not in stored["subject"]


def test_duplicates_and_manual_leads_send_no_alert(
    client: Any, owner: SignedIn, texts: dict[str, Any], intake_unlimited: None
) -> None:
    set_inbox(owner, "sales-inbox@example.com")
    submit_ok(client, enquiry(texts, 1))
    submit_ok(client, enquiry(texts, 1))  # same phone, no project, within 24 h → duplicate
    manual = owner.client.post(
        LEADS,
        json={
            "name": "Walk In",
            "phone": "98765 11111",
            "source": "phone",
            "consent_note": "Agreed on the phone to be called back about the project.",
        },
        headers=owner.headers(),
    )
    assert manual.status_code == 201, manual.text
    assert len(mail_to("sales-inbox@example.com", "lead_alert")) == 1


def test_without_an_inbox_every_active_super_admin_is_told(
    client: Any, owner: SignedIn, texts: dict[str, Any], intake_unlimited: None
) -> None:
    make_user("super_admin", email="second-owner@example.com")
    make_user("super_admin", email="former@example.com", is_active=False)
    make_user("admin", email="admin@example.com")
    submit_ok(client, enquiry(texts, 2))
    told = {m.to for m in mail_to(owner.user.email) + mail_to("second-owner@example.com")}
    assert told == {"owner@example.com", "second-owner@example.com"}
    assert mail_to("former@example.com") == [] and mail_to("admin@example.com") == []


def test_a_site_visit_request_sends_one_email_with_the_day(
    client: Any,
    owner: SignedIn,
    texts: dict[str, Any],
    intake_unlimited: None,
    project: dict[str, Any],
) -> None:
    set_inbox(owner, "sales-inbox@example.com")
    day = today_ist() + timedelta(days=3)
    body = enquiry(texts, 3, project_slug=project["slug"], source="site_visit")
    submit_ok(
        client,
        {**body, "preferred_date": day.isoformat(), "preferred_slot": "evening"},
        "site-visits",
    )
    mails = mail_to("sales-inbox@example.com")
    assert [m.template for m in mails] == ["visit_requested"]
    assert "Evening" in mails[0].text and str(day.year) in mails[0].text
    assert project["name"] in mails[0].text and "98765 00003" not in mails[0].text


def test_round_robin_owner_gets_the_new_lead_too(
    client: Any, owner: SignedIn, texts: dict[str, Any], intake_unlimited: None
) -> None:
    sales = make_user("sales", email="sales1@example.com", name="Sales 1")
    r = owner.client.patch(
        f"{SETTINGS}/lead_routing",
        json={
            "mode": "round_robin",
            "round_robin_user_ids": [str(sales.id)],
            "inbox_email": "inbox@example.com",
        },
        headers=owner.headers(),
    )
    assert r.status_code == 200, r.text
    submit_ok(client, enquiry(texts, 4))
    [mine] = mail_to("sales1@example.com", "lead_assigned")
    assert "Hello Sales 1" in mine.text and "now yours" in mine.text
    assert len(mail_to("inbox@example.com", "lead_alert")) == 1


def test_assigning_a_lead_emails_the_new_owner_but_not_yourself(
    app: FastAPI,
    client: Any,
    owner: SignedIn,
    texts: dict[str, Any],
    intake_unlimited: None,
    db: Session,
) -> None:
    sales = make_user("sales", email="sales2@example.com", name="Sales 2")
    reference = submit_ok(client, enquiry(texts, 5))
    lead = lead_id(db, reference)
    r = owner.client.patch(
        f"{LEADS}/{lead}", json={"owner_user_id": str(sales.id)}, headers=owner.headers()
    )
    assert r.status_code == 200, r.text
    [mail] = mail_to("sales2@example.com", "lead_assigned")
    assert reference in mail.subject and "98765 00005" not in mail.text
    owner.client.patch(
        f"{LEADS}/{lead}", json={"owner_user_id": str(owner.user.id)}, headers=owner.headers()
    )
    assert mail_to(owner.user.email, "lead_assigned") == []
    owner.client.patch(f"{LEADS}/{lead}", json={"owner_user_id": None}, headers=owner.headers())
    assert len(mail_to("sales2@example.com", "lead_assigned")) == 1


def test_an_erased_or_spam_lead_is_never_announced(
    client: Any,
    owner: SignedIn,
    texts: dict[str, Any],
    intake_unlimited: None,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_inbox(owner, "sales-inbox@example.com")
    monkeypatch.setattr("empire_api.leads.routes_public.drain_soon", lambda background: None)
    reference = submit_ok(client, enquiry(texts, 6))
    lead = lead_id(db, reference)
    erased = owner.client.delete(f"{LEADS}/{lead}", headers=owner.headers())
    assert erased.status_code == 204, erased.text
    assert mail_to("sales-inbox@example.com", "lead_alert") == []
    spam_ref = submit_ok(client, enquiry(texts, 12))
    spam = owner.client.patch(
        f"{LEADS}/{lead_id(db, spam_ref)}", json={"is_spam": True}, headers=owner.headers()
    )
    assert spam.status_code == 200, spam.text
    assert mail_to("sales-inbox@example.com", "lead_alert") == []


def test_a_retried_event_never_sends_twice(
    client: Any, owner: SignedIn, texts: dict[str, Any], intake_unlimited: None, db: Session
) -> None:
    set_inbox(owner, "sales-inbox@example.com")
    submit_ok(client, enquiry(texts, 8))
    assert len(mail_to("sales-inbox@example.com", "lead_alert")) == 1
    db.execute(
        update(OutboxEvent).where(OutboxEvent.type == "lead.created").values(status="pending")
    )
    db.commit()
    assert len(mail_to("sales-inbox@example.com", "lead_alert")) == 1
    assert (
        len(db.scalars(select(EmailMessage).where(EmailMessage.template == "lead_alert")).all())
        == 1
    )


def test_lead_email_html_is_plain_and_ours(
    client: Any, owner: SignedIn, texts: dict[str, Any], intake_unlimited: None
) -> None:
    set_inbox(owner, "sales-inbox@example.com")
    submit_ok(client, enquiry(texts, 9, name="Asha <b>Bold</b>"))
    html = all_mail()[-1]["html"]
    assert "<img" not in html and "<script" not in html and "<link" not in html
    assert "@import" not in html and "url(" not in html
    assert "&lt;b&gt;Bold&lt;/b&gt;" in html and "<b>Bold</b>" not in html
    assert '<html lang="en">' in html and "<title>" in html


def test_company_lines_are_placeholders_until_filled(
    client: Any, owner: SignedIn, texts: dict[str, Any], intake_unlimited: None
) -> None:
    set_inbox(owner, "sales-inbox@example.com")
    submit_ok(client, enquiry(texts, 10))
    assert "[Company name]" in all_mail()[-1]["text"]
    owner.client.patch(
        f"{SETTINGS}/company", json={"brand_name": "Empire Test Brand"}, headers=owner.headers()
    )
    owner.client.patch(
        f"{SETTINGS}/email",
        json={"sender_name": "Empire Sales", "reply_to": "sales@example.com"},
        headers=owner.headers(),
    )
    submit_ok(client, enquiry(texts, 11))
    latest = all_mail()
    newest = max(latest, key=lambda m: m["sent_at"])
    assert "Empire Test Brand" in newest["text"]
    assert newest["from"].startswith("Empire Sales <") and newest["reply_to"] == "sales@example.com"


# --- Failed emails on the dashboard --------------------------------------------------------


def test_dead_emails_show_on_the_dashboard_without_personal_data(
    app: FastAPI, owner: SignedIn, db: Session
) -> None:
    with get_sessionmaker()() as session:
        for _ in range(3):
            session.add(
                OutboxEvent(
                    type="lead.created",
                    aggregate_type="lead",
                    aggregate_id="x",
                    status="dead",
                    payload={},
                )
            )
        session.add(
            OutboxEvent(
                type="project.published",
                aggregate_type="project",
                aggregate_id="y",
                status="dead",
                payload={},
            )
        )
        session.commit()
    tasks = owner.client.get("/api/v1/admin/dashboard").json()["tasks"]
    [task] = [t for t in tasks if t["key"] == "email.failed"]
    assert task["label"] == "3 emails couldn't be sent"
    assert task["link"] == "/admin/settings?tab=integrations"
    sales = staff_client(app, "sales")
    assert "email.failed" not in {
        t["key"] for t in sales.client.get("/api/v1/admin/dashboard").json()["tasks"]
    }
    overview = owner.client.get(SETTINGS).json()
    assert overview["integrations"]["email"]["failed_last_7_days"] == 3


def test_no_password_or_token_rows_leak_into_the_sent_mail_log(
    owner: SignedIn, db: Session
) -> None:
    owner.client.post(
        "/api/v1/admin/users",
        json={"email": "logcheck@example.com", "name": "Log Check", "role": "sales"},
        headers=owner.headers(),
    )
    drain()
    rows = db.execute(text("SELECT * FROM email_message")).mappings().all()
    assert rows and all("logcheck" not in repr(dict(r)) for r in rows)
    tokens = db.scalars(select(PasswordResetToken.token_hash)).all()
    link = mail_to("logcheck@example.com")[0].links[0]
    assert link.split("token=")[1] not in repr(tokens)
