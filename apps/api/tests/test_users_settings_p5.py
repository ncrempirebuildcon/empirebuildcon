"""Phase 4 part 5 additions around users and the audit log: the list's status, two-factor and
filters, invites that never return the link, the role table, masked audit IPs with the actor's
role and IST date filters, `Me`, flags with plain-English titles, consent-text purposes, and the
SAMPLE accounts seed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from conftest import SignedIn, make_user, new_client, sign_in
from empire_api.config import get_settings
from empire_api.db import get_sessionmaker
from empire_api.platform import audit
from empire_api.platform.models import AuditLog
from empire_api.users import seed as user_seed
from empire_api.users.audit_log import display_ip
from empire_api.users.models import User
from empire_api.users.role_docs import PERMISSION_GROUPS, ROLE_SUMMARIES
from empire_api.users.roles import PERMISSIONS, ROLE_KEYS
from empire_api.users.seed import SAMPLE_USERS, SampleUsersRefusedError, seed_sample_users
from leads_support import staff_client
from two_factor_support import login, mail_to, turn_on, use_clock

USERS = "/api/v1/admin/users"
AUDIT = "/api/v1/admin/audit-log"


# --- Users list ----------------------------------------------------------------------------


def test_the_list_shows_status_and_two_factor(
    app: FastAPI, owner: SignedIn, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = use_clock(monkeypatch)
    invited = owner.client.post(
        USERS,
        json={"email": "inv@example.com", "name": "Invited", "role": "sales"},
        headers=owner.headers(),
    ).json()
    assert invited["status"] == "invited" and invited["invite_sent_at"] is not None
    make_user("sales", email="off@example.com", is_active=False)
    locked = make_user("sales", email="locked@example.com")
    with get_sessionmaker()() as session:
        session.execute(
            update(User)
            .where(User.id == locked.id)
            .values(locked_until=datetime.now(UTC) + timedelta(minutes=10))
        )
        session.commit()
    admin_user = make_user("admin", email="admin@example.com")
    turn_on(sign_in(new_client(app), admin_user), clock)
    items = {u["email"]: u for u in owner.client.get(USERS).json()["items"]}
    assert items["inv@example.com"]["status"] == "invited"
    assert items["off@example.com"]["status"] == "deactivated"
    assert items["locked@example.com"]["status"] == "locked"
    assert items["owner@example.com"]["status"] == "active"
    assert items["admin@example.com"]["two_factor_enabled"] is True
    assert items["owner@example.com"]["two_factor_enabled"] is False
    assert items["owner@example.com"]["invite_sent_at"] is None


def test_the_list_filters_by_role_and_status(owner: SignedIn) -> None:
    make_user("sales", email="s1@example.com")
    make_user("sales", email="s2@example.com", is_active=False)
    make_user("marketing", email="m1@example.com", password=None)

    def emails(**params: str) -> set[str]:
        r = owner.client.get(USERS, params=params)
        assert r.status_code == 200, r.text
        return {u["email"] for u in r.json()["items"]}

    assert emails(role="sales") == {"s1@example.com", "s2@example.com"}
    assert emails(status="deactivated") == {"s2@example.com"}
    assert emails(status="invited") == {"m1@example.com"}
    assert emails(status="active") == {"owner@example.com", "s1@example.com"}
    assert emails(role="sales", status="active") == {"s1@example.com"}
    assert owner.client.get(USERS, params={"status": "gone"}).status_code == 422
    assert owner.client.get(USERS, params={"role": "owner"}).status_code == 422


def test_an_invite_never_returns_the_link(owner: SignedIn) -> None:
    r = owner.client.post(
        USERS,
        json={"email": "x@example.com", "name": "X Person", "role": "admin"},
        headers=owner.headers(),
    )
    assert r.status_code == 201
    assert "token" not in r.json() and "link" not in r.json()
    assert "/admin/setup" not in r.text


def test_send_reset_sends_a_setup_link_to_someone_never_set_up(owner: SignedIn) -> None:
    invited = owner.client.post(
        USERS,
        json={"email": "again@example.com", "name": "Again", "role": "sales"},
        headers=owner.headers(),
    ).json()
    r = owner.client.post(f"{USERS}/{invited['id']}/send-reset", headers=owner.headers())
    assert r.status_code == 204
    templates = [m.template for m in mail_to("again@example.com")]
    assert templates == ["setup_link", "setup_link"]


def test_deactivate_and_reactivate(app: FastAPI, owner: SignedIn) -> None:
    sales = staff_client(app, "sales")
    off = owner.client.patch(
        f"{USERS}/{sales.user.id}", json={"is_active": False}, headers=owner.headers()
    )
    assert off.status_code == 200 and off.json()["status"] == "deactivated"
    assert sales.client.get("/api/v1/auth/me").status_code == 401
    on = owner.client.patch(
        f"{USERS}/{sales.user.id}", json={"is_active": True}, headers=owner.headers()
    )
    assert on.json()["status"] == "active"


# --- Roles and permissions -----------------------------------------------------------------


def test_roles_have_a_summary_and_a_count(owner: SignedIn) -> None:
    make_user("sales", email="s1@example.com")
    make_user("sales", email="s2@example.com")
    make_user("sales", email="s3@example.com", is_active=False)
    roles = {r["key"]: r for r in owner.client.get("/api/v1/admin/roles").json()}
    assert roles["sales"]["user_count"] == 2 and roles["super_admin"]["user_count"] == 1
    assert roles["admin"]["user_count"] == 0
    assert roles["sales"]["summary"] == ROLE_SUMMARIES["sales"]


def test_the_permission_table_is_the_matrix(owner: SignedIn, app: FastAPI) -> None:
    rows = owner.client.get("/api/v1/admin/permissions").json()
    assert [r["key"] for r in rows] == list(PERMISSIONS)
    by_key = {r["key"]: r for r in rows}
    assert by_key["leads.erase"]["roles"] == ["super_admin"]
    assert by_key["marketing.tracking"]["roles"] == ["super_admin", "admin", "marketing"]
    assert by_key["users.manage"]["allows"] == "Accounts and roles"
    assert by_key["seo.manage"]["group"] == "Content & SEO"
    assert staff_client(app, "admin").client.get("/api/v1/admin/permissions").status_code == 403


def test_every_permission_has_a_group_and_every_role_a_summary() -> None:
    assert set(PERMISSION_GROUPS) == set(PERMISSIONS)
    assert set(ROLE_SUMMARIES) == set(ROLE_KEYS)


# --- Audit log -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stored", "shown"),
    [
        ("49.36.12.0/24", "49.36.xxx.xxx"),
        ("203.0.113.0/24", "203.0.xxx.xxx"),
        ("2001:db8:1234::/48", "2001:db8::/32"),
        (None, None),
        ("garbage", None),
    ],
)
def test_ips_are_shown_coarser_than_stored(stored: str | None, shown: str | None) -> None:
    assert display_ip(stored) == shown


def _audit(db: Session, action: str, actor: Any, ip: str | None, when: datetime) -> None:
    """An audit row dated `when`. WHY set at insert: the table refuses UPDATE (migration 0006)."""
    row = audit.record(db, action=action, entity_type="user", entity_id="x", actor_id=actor, ip=ip)
    row.created_at = when
    db.commit()


def _empty_audit_log(db: Session) -> None:
    """WHY TRUNCATE: the trigger refuses DELETE on audit_log; row triggers don't fire on it."""
    db.execute(text("TRUNCATE audit_log"))
    db.commit()


def test_the_audit_log_masks_ips_and_names_the_actors_role(owner: SignedIn, db: Session) -> None:
    _empty_audit_log(db)
    now = datetime.now(UTC)
    _audit(db, "user.unlocked", owner.user.id, "49.36.12.34", now)
    _audit(db, "user.locked", None, "2001:db8:1234:5678::1", now)
    items = owner.client.get(AUDIT).json()["items"]
    assert {i["ip"] for i in items} == {"49.36.xxx.xxx", "2001:db8::/32"}
    by_action = {i["action"]: i for i in items}
    assert by_action["user.unlocked"]["actor"] == {
        "id": str(owner.user.id), "name": owner.user.name, "role": "super_admin",
    }  # fmt: skip
    assert by_action["user.locked"]["actor"] is None
    assert "49.36.12" not in owner.client.get(AUDIT).text


def test_audit_filters_person_system_prefix_and_ist_days(owner: SignedIn, db: Session) -> None:
    _empty_audit_log(db)
    # 24 Oct 2026 23:30 IST is 18:00 UTC; 25 Oct 00:30 IST is 19:00 UTC on the 24th.
    late_24 = datetime(2026, 10, 24, 18, 0, tzinfo=UTC)
    early_25 = datetime(2026, 10, 24, 19, 0, tzinfo=UTC)
    _audit(db, "auth.login", owner.user.id, None, late_24)
    _audit(db, "user.locked", None, None, early_25)
    _audit(db, "auth_like.other", owner.user.id, None, early_25)

    def actions(**params: Any) -> list[str]:
        r = owner.client.get(AUDIT, params=params)
        assert r.status_code == 200, r.text
        return sorted(i["action"] for i in r.json()["items"])

    assert actions(**{"from": "2026-10-25", "to": "2026-10-25"}) == [
        "auth_like.other",
        "user.locked",
    ]
    assert actions(**{"from": "2026-10-24", "to": "2026-10-24"}) == ["auth.login"]
    assert actions(action_prefix="auth.") == ["auth.login"]  # "_" and "%" are not wildcards
    assert actions(action_prefix="auth_") == ["auth_like.other"]
    assert actions(system="true") == ["user.locked"]
    assert actions(actor_id=str(owner.user.id)) == ["auth.login", "auth_like.other"]
    bad = owner.client.get(AUDIT, params={"from": "2026-10-25", "to": "2026-10-24"})
    assert bad.status_code == 422 and bad.json()["errors"][0]["field"] == "to"


def test_nothing_here_edits_the_audit_log(owner: SignedIn, db: Session) -> None:
    """INVARIANT (platform/models.AuditLog): reading the log changes no row."""
    before = db.execute(text("SELECT id, action, changes FROM audit_log ORDER BY id")).all()
    owner.client.get(AUDIT, params={"action_prefix": "auth."})
    db.expire_all()
    assert db.execute(text("SELECT id, action, changes FROM audit_log ORDER BY id")).all() == before


# --- Me ------------------------------------------------------------------------------------


def test_me_says_what_two_factor_means_for_you(app: FastAPI, owner: SignedIn) -> None:
    me = owner.client.get("/api/v1/auth/me").json()
    assert me["can_use_two_factor"] is True and me["two_factor_required"] is False
    assert me["two_factor_enabled"] is False and me["recovery_codes_left"] is None
    assert me["status"] == "active"
    sales = staff_client(app, "sales").client.get("/api/v1/auth/me").json()
    assert sales["can_use_two_factor"] is False


# --- Flags ---------------------------------------------------------------------------------


def test_flags_have_titles_and_say_who_may_switch_them(app: FastAPI, owner: SignedIn) -> None:
    flags = {f["key"]: f for f in owner.client.get("/api/v1/admin/flags").json()}
    assert flags["admin_2fa"]["title"] == "Two-factor sign-in for admins"
    assert flags["admin_2fa"]["who_can_switch"].startswith("Super-admins only")
    assert flags["chat_widget"]["can_switch"] is True
    assert flags["listings"]["can_switch"] is False
    assert (
        flags["listings"]["cannot_switch_reason"]
        == "This feature is not built yet, so it can't be switched on."
    )
    marketing = {
        f["key"]: f for f in staff_client(app, "marketing").client.get("/api/v1/admin/flags").json()
    }
    assert marketing["chat_widget"]["can_switch"] is False
    assert "flags.manage" in marketing["chat_widget"]["cannot_switch_reason"]


# --- Consent texts -------------------------------------------------------------------------


def test_consent_texts_say_who_published_them_and_which_is_current(
    owner: SignedIn, texts: dict[str, Any]
) -> None:
    kinds = {k["kind"]: k for k in owner.client.get("/api/v1/admin/consent-texts/current").json()}
    assert set(kinds) == {"lead_form", "marketing", "brochure", "cookies", "chat"}
    assert (
        kinds["lead_form"]["current_version"] == 1
        and kinds["lead_form"]["current"]["is_draft_text"] is True
    )
    assert kinds["cookies"]["current"] is None and kinds["cookies"]["versions"] == 0
    assert kinds["lead_form"]["current"]["published_by"] is None  # seeded
    draft = owner.client.post(
        "/api/v1/admin/consent-texts",
        json={
            "kind": "lead_form",
            "body": "Approved wording for the enquiry form.",
            "checkbox_label": "Contact me about this enquiry.",
        },
        headers=owner.headers(),
    ).json()
    assert draft["is_draft_text"] is False and draft["published_by"] is None
    newer = {k["kind"]: k for k in owner.client.get("/api/v1/admin/consent-texts/current").json()}
    assert (
        newer["lead_form"]["has_unpublished_newer"] is True
        and newer["lead_form"]["latest_version"] == 2
    )
    published = owner.client.post(
        f"/api/v1/admin/consent-texts/{draft['id']}/publish", headers=owner.headers()
    ).json()
    assert published["published_by"] == {"id": str(owner.user.id), "name": owner.user.name}
    after = {k["kind"]: k for k in owner.client.get("/api/v1/admin/consent-texts/current").json()}
    assert (
        after["lead_form"]["current_version"] == 2
        and after["lead_form"]["has_unpublished_newer"] is False
    )


# --- Sample accounts -----------------------------------------------------------------------


def test_sample_accounts_are_invited_only_and_never_in_production(
    db: Session, monkeypatch: pytest.MonkeyPatch, app: FastAPI
) -> None:
    result = seed_sample_users(db)
    db.commit()
    assert result.added == len(SAMPLE_USERS)
    assert seed_sample_users(db).added == 0
    rows = db.scalars(select(User).where(User.email.like("sample.%"))).all()
    assert all(u.name.startswith("Sample ") and u.password_hash is None for u in rows)
    assert all(u.email.endswith("@example.com") for u in rows)
    assert login(new_client(app), rows[0].email, "anything at all").status_code == 401
    production = get_settings().model_copy(update={"app_env": "production"})
    monkeypatch.setattr(user_seed, "get_settings", lambda: production)
    with pytest.raises(SampleUsersRefusedError):
        seed_sample_users(db)


def test_audit_entries_are_never_written_by_reads(db: Session, owner: SignedIn) -> None:
    count = db.scalar(select(text("count(*)")).select_from(AuditLog))
    owner.client.get(USERS)
    owner.client.get("/api/v1/admin/roles")
    assert db.scalar(select(text("count(*)")).select_from(AuditLog)) == count
