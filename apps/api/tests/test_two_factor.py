"""Two-factor sign-in (SECURITY.md §1, flag admin_2fa): the RFC 6238 code, replay refusal, the
two-step sign-in and its cookie, lockout on wrong codes (D-027), forced set-up, recovery codes,
My account, the super-admin's reset, and the flag rule."""

from __future__ import annotations

import base64
import concurrent.futures
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from conftest import GOOD_PASSWORD, SignedIn, make_user, new_client, sign_in
from empire_api.cli import app as cli_app
from empire_api.config import Settings, get_settings
from empire_api.db import get_engine, get_sessionmaker
from empire_api.integrations.outbox_drain import cleanup
from empire_api.main import create_app
from empire_api.platform.models import AuditLog, OutboxEvent
from empire_api.users import lockout, totp
from empire_api.users import sign_in as sign_in_module
from empire_api.users.lockout import LOCKED_MESSAGE
from empire_api.users.models import SignInChallenge, TwoFactorRecoveryCode, User, UserTwoFactor
from empire_api.users.two_factor import WRONG_CODE
from leads_support import captured_logs
from test_security_review import EDGE_KEY, edge_client
from two_factor_support import TWO_FA, Clock, code, key_of, login, turn_on, use_clock

FLAGS = "/api/v1/admin/flags"


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    return use_clock(monkeypatch)


def flag_on(owner: SignedIn) -> None:
    with get_sessionmaker()() as db:
        db.execute(text("UPDATE feature_flag SET enabled = true WHERE key = 'admin_2fa'"))
        db.commit()


# --- RFC 6238 ------------------------------------------------------------------------------

RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()


@pytest.mark.parametrize(
    ("unix_time", "expected"),
    [
        (59, "94287082"),
        (1111111109, "07081804"),
        (1111111111, "14050471"),
        (1234567890, "89005924"),
        (2000000000, "69279037"),
        (20000000000, "65353130"),
    ],
)
def test_rfc_6238_appendix_b_sha1_vectors(unix_time: int, expected: str) -> None:
    moment = datetime.fromtimestamp(unix_time, UTC)
    assert totp.code_at(RFC_SECRET, moment, digits=8) == expected


def test_codes_match_one_step_either_side_only() -> None:
    secret = totp.new_secret()
    now = datetime(2026, 10, 25, 12, 0, 15, tzinfo=UTC)
    step = totp.step_at(now)
    for offset in (-1, 0, 1):
        moment = now + timedelta(seconds=30 * offset)
        assert totp.matching_step(secret, totp.code_at(secret, moment), now) == step + offset
    far = totp.code_at(secret, now + timedelta(seconds=90))
    assert totp.matching_step(secret, far, now) is None
    assert totp.matching_step(secret, "12345", now) is None
    assert totp.matching_step(secret, "abcdef", now) is None


def test_secret_and_link_follow_the_key_uri_format() -> None:
    secret = totp.new_secret()
    assert len(base64.b32decode(secret + "=" * (-len(secret) % 8))) == 20
    uri = totp.provisioning_uri(secret, "owner@example.com")
    assert uri.startswith("otpauth://totp/Empire%20CMS%3Aowner%40example.com?")
    assert f"secret={secret}" in uri and "digits=6" in uri and "period=30" in uri


# --- My account: set-up ------------------------------------------------------------------


def test_setup_needs_the_password_and_shows_a_qr_once(owner: SignedIn, db: Session) -> None:
    wrong = owner.client.post(
        f"{TWO_FA}/setup", json={"current_password": "not my password!"}, headers=owner.headers()
    )
    assert wrong.status_code == 400
    assert wrong.json()["errors"][0]["field"] == "current_password"
    started = owner.client.post(
        f"{TWO_FA}/setup", json={"current_password": GOOD_PASSWORD}, headers=owner.headers()
    )
    assert started.status_code == 200
    body = started.json()
    assert body["qr_svg_data_url"].startswith("data:image/svg+xml")
    assert body["otpauth_uri"].startswith("otpauth://totp/")
    assert body["digits"] == 6 and body["period_seconds"] == 30
    # SECURITY: stored encrypted, not confirmed yet, so sign-in doesn't ask for it.
    row = db.get(UserTwoFactor, owner.user.id)
    assert row is not None and row.confirmed_at is None
    assert key_of(body) not in row.secret_encrypted
    assert owner.client.get("/api/v1/auth/me").json()["two_factor_enabled"] is False


def test_confirming_turns_it_on_and_gives_ten_hashed_recovery_codes(
    owner: SignedIn, clock: Clock, db: Session
) -> None:
    enrolled = turn_on(owner, clock)
    assert len(enrolled.recovery_codes) == 10
    assert len(set(enrolled.recovery_codes)) == 10
    me = owner.client.get("/api/v1/auth/me").json()
    assert me["two_factor_enabled"] is True and me["recovery_codes_left"] == 10
    stored = db.scalars(select(TwoFactorRecoveryCode.code_hash)).all()
    for recovery in enrolled.recovery_codes:
        assert all(recovery.replace("-", "") not in h for h in stored)
    assert {e.type for e in db.scalars(select(OutboxEvent))} >= {"user.two_factor_enabled"}


def test_turning_it_on_signs_out_other_sessions(
    app: FastAPI, owner: SignedIn, clock: Clock
) -> None:
    other = sign_in(new_client(app), owner.user)
    turn_on(owner, clock)
    assert other.client.get("/api/v1/auth/me").status_code == 401
    assert owner.client.get("/api/v1/auth/me").status_code == 200


def test_a_wrong_confirmation_code_is_refused(owner: SignedIn, clock: Clock) -> None:
    owner.client.post(
        f"{TWO_FA}/setup", json={"current_password": GOOD_PASSWORD}, headers=owner.headers()
    )
    r = owner.client.post(
        f"{TWO_FA}/setup/confirm", json={"code": "000000"}, headers=owner.headers()
    )
    assert r.status_code == 400 and r.json()["detail"] == WRONG_CODE


def test_only_admins_and_super_admins_can_turn_it_on(app: FastAPI) -> None:
    for role in ("sales", "marketing", "content_editor"):
        signed = sign_in(new_client(app), make_user(role, email=f"{role}@example.com"))
        r = signed.client.post(
            f"{TWO_FA}/setup", json={"current_password": GOOD_PASSWORD}, headers=signed.headers()
        )
        assert r.status_code == 403, role
    admin = sign_in(new_client(app), make_user("admin", email="admin@example.com"))
    r = admin.client.post(
        f"{TWO_FA}/setup", json={"current_password": GOOD_PASSWORD}, headers=admin.headers()
    )
    assert r.status_code == 200


def test_setup_needs_csrf(owner: SignedIn) -> None:
    r = owner.client.post(f"{TWO_FA}/setup", json={"current_password": GOOD_PASSWORD})
    assert r.status_code == 403


# --- Sign-in with two-factor --------------------------------------------------------------


def test_a_right_password_alone_starts_no_session(
    app: FastAPI, owner: SignedIn, clock: Clock, db: Session
) -> None:
    enrolled = turn_on(owner, clock)
    fresh = new_client(app)
    first = login(fresh, owner.user.email)
    assert first.status_code == 202
    assert first.json() == {
        "status": "two_factor_required",
        "step": "verify",
        "email": owner.user.email,
        "expires_in_seconds": 300,
    }
    cookie = first.headers["set-cookie"]
    assert cookie.startswith("__Host-empire_2fa=")
    for flag in ("HttpOnly", "Secure", "Path=/", "SameSite=strict", "Max-Age=300"):
        assert flag in cookie
    assert "Domain" not in cookie and "__Host-empire_session" not in cookie
    assert fresh.get("/api/v1/auth/me").status_code == 401
    done = fresh.post(f"{TWO_FA}/verify", json={"code": code(enrolled.secret, clock)})
    assert done.status_code == 200, done.text
    assert done.json()["email"] == owner.user.email and done.json()["csrf_token"]
    assert "__Host-empire_session=" in done.headers["set-cookie"]
    assert fresh.get("/api/v1/auth/me").status_code == 200
    login_row = db.scalars(select(AuditLog).where(AuditLog.action == "auth.login")).all()[-1]
    assert login_row.changes == {"second_step": [None, "totp"]}


def test_a_seen_code_can_not_be_used_again(app: FastAPI, owner: SignedIn, clock: Clock) -> None:
    """Replay refusal: each 30-second step is accepted once per account."""
    enrolled = turn_on(owner, clock)
    seen = code(enrolled.secret, clock)
    first = new_client(app)
    login(first, owner.user.email)
    assert first.post(f"{TWO_FA}/verify", json={"code": seen}).status_code == 200
    second = new_client(app)
    login(second, owner.user.email)
    r = second.post(f"{TWO_FA}/verify", json={"code": seen})
    assert r.status_code == 401 and r.json()["detail"] == WRONG_CODE
    clock.next_step()
    assert (
        second.post(f"{TWO_FA}/verify", json={"code": code(enrolled.secret, clock)}).status_code
        == 200
    )


def test_the_same_code_twice_at_once_starts_one_session(
    app: FastAPI, owner: SignedIn, clock: Clock
) -> None:
    enrolled = turn_on(owner, clock)
    clients = [new_client(app) for _ in range(2)]
    for c in clients:
        login(c, owner.user.email)
    right = code(enrolled.secret, clock)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(
            pool.map(
                lambda c: c.post(f"{TWO_FA}/verify", json={"code": right}).status_code, clients
            )
        )
    assert statuses == [200, 401]


def test_the_challenge_is_single_use_and_expires(
    app: FastAPI, owner: SignedIn, clock: Clock, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    enrolled = turn_on(owner, clock)
    fresh = new_client(app)
    login(fresh, owner.user.email)
    token = fresh.cookies.get("__Host-empire_2fa")
    assert (
        fresh.post(f"{TWO_FA}/verify", json={"code": code(enrolled.secret, clock)}).status_code
        == 200
    )
    # The cookie is cleared; replaying the old one is refused even with a new code.
    clock.next_step()
    replay = new_client(app)
    replay.cookies.set("__Host-empire_2fa", token or "", domain="testserver", path="/")
    r = replay.post(f"{TWO_FA}/verify", json={"code": code(enrolled.secret, clock)})
    assert r.status_code == 401 and r.json()["detail"] == sign_in_module.CHALLENGE_EXPIRED
    # Expired after 5 minutes.
    late = new_client(app)
    login(late, owner.user.email)
    db.execute(text("UPDATE sign_in_challenge SET expires_at = now() - interval '1 second'"))
    db.commit()
    r = late.post(f"{TWO_FA}/verify", json={"code": code(enrolled.secret, clock)})
    assert r.status_code == 401 and r.json()["detail"] == sign_in_module.CHALLENGE_EXPIRED
    stored = db.scalars(select(SignInChallenge.token_hash)).all()
    assert token not in stored  # SECURITY: only the hash is stored


def test_verify_without_a_challenge_is_401(client: TestClient) -> None:
    r = client.post(f"{TWO_FA}/verify", json={"code": "123456"})
    assert r.status_code == 401


def test_a_recovery_code_works_once(
    app: FastAPI, owner: SignedIn, clock: Clock, db: Session
) -> None:
    enrolled = turn_on(owner, clock)
    recovery = enrolled.recovery_codes[0].lower().replace("-", " ")
    first = new_client(app)
    login(first, owner.user.email)
    r = first.post(f"{TWO_FA}/verify", json={"recovery_code": recovery})
    assert r.status_code == 200
    assert r.json()["recovery_codes_left"] == 9
    events = [e.type for e in db.scalars(select(OutboxEvent))]
    assert "user.recovery_code_used" in events
    again = new_client(app)
    login(again, owner.user.email)
    r = again.post(f"{TWO_FA}/verify", json={"recovery_code": enrolled.recovery_codes[0]})
    assert r.status_code == 401


def test_a_proof_is_one_code_or_one_recovery_code(
    app: FastAPI, owner: SignedIn, clock: Clock
) -> None:
    turn_on(owner, clock)
    fresh = new_client(app)
    login(fresh, owner.user.email)
    for body in ({}, {"code": "123456", "recovery_code": "ABCDE-FGHJK"}):
        r = fresh.post(f"{TWO_FA}/verify", json=body)
        assert r.status_code == 422


# --- Lockout (D-027 for codes) ------------------------------------------------------------


def test_wrong_codes_lock_like_wrong_passwords(
    app: FastAPI, owner: SignedIn, clock: Clock, db: Session
) -> None:
    """INVARIANT: at most 5 checks (passwords or codes) per account and network per 15 min."""
    enrolled = turn_on(owner, clock)
    fresh = new_client(app)
    assert login(fresh, owner.user.email).status_code == 202  # attempt 1 (not cleared)
    statuses = [
        fresh.post(f"{TWO_FA}/verify", json={"code": "000000"}).status_code for _ in range(5)
    ]
    assert statuses == [401, 401, 401, 401, 429]
    blocked = fresh.post(f"{TWO_FA}/verify", json={"code": code(enrolled.secret, clock)})
    assert blocked.status_code == 429 and blocked.json()["detail"] == LOCKED_MESSAGE
    assert "retry-after" in blocked.headers
    # The password step is blocked too, and the 5th failure noted the lock.
    assert login(new_client(app), owner.user.email).status_code == 429
    assert db.scalars(select(AuditLog).where(AuditLog.action == "user.locked")).first()
    assert "user.locked" in [e.type for e in db.scalars(select(OutboxEvent))]


def test_a_right_password_does_not_reset_the_code_counter(
    app: FastAPI, owner: SignedIn, clock: Clock
) -> None:
    """Otherwise 'password, 4 wrong codes, password, 4 wrong codes…' would never stop."""
    turn_on(owner, clock)
    fresh = new_client(app)
    login(fresh, owner.user.email)  # 1
    for _ in range(3):
        fresh.post(f"{TWO_FA}/verify", json={"code": "000000"})  # 2, 3, 4
    assert login(fresh, owner.user.email).status_code == 202  # 5
    assert fresh.post(f"{TWO_FA}/verify", json={"code": "000000"}).status_code == 429  # 6


def test_a_completed_sign_in_clears_the_counter(
    app: FastAPI, owner: SignedIn, clock: Clock
) -> None:
    enrolled = turn_on(owner, clock)
    fresh = new_client(app)
    login(fresh, owner.user.email)
    for _ in range(3):
        fresh.post(f"{TWO_FA}/verify", json={"code": "000000"})
    assert (
        fresh.post(f"{TWO_FA}/verify", json={"code": code(enrolled.secret, clock)}).status_code
        == 200
    )
    clock.next_step()
    again = new_client(app)
    for _ in range(4):
        assert login(again, owner.user.email).status_code == 202


def test_codes_are_capped_per_account_across_networks(
    app: FastAPI, owner: SignedIn, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lockout, "CODE_LIMIT_PER_HOUR", 3)
    turn_on(owner, clock)  # the set-up's confirmation code is the first of the 3
    fresh = new_client(app)
    login(fresh, owner.user.email)
    assert fresh.post(f"{TWO_FA}/verify", json={"code": "000000"}).status_code == 401
    assert fresh.post(f"{TWO_FA}/verify", json={"code": "000000"}).status_code == 401
    assert fresh.post(f"{TWO_FA}/verify", json={"code": "000000"}).status_code == 429


def test_the_challenge_is_bound_to_the_network(owner: SignedIn, clock: Clock) -> None:
    enrolled = turn_on(owner, clock)
    app = create_app(
        Settings(**{**get_settings().model_dump(), "edge_proxy_key": SecretStr(EDGE_KEY)})
    )
    home = edge_client(app, "203.0.113.10")
    assert login(home, owner.user.email).status_code == 202
    token = home.cookies.get("__Host-empire_2fa")
    elsewhere = edge_client(app, "198.51.100.20")
    elsewhere.cookies.set("__Host-empire_2fa", token or "", domain="testserver", path="/")
    r = elsewhere.post(f"{TWO_FA}/verify", json={"code": code(enrolled.secret, clock)})
    assert r.status_code == 401 and r.json()["detail"] == sign_in_module.CHALLENGE_EXPIRED
    assert (
        home.post(f"{TWO_FA}/verify", json={"code": code(enrolled.secret, clock)}).status_code
        == 200
    )


# --- Forced set-up (flag on) --------------------------------------------------------------


def test_with_the_flag_on_an_admin_without_two_factor_must_set_it_up(
    app: FastAPI, owner: SignedIn, clock: Clock, db: Session
) -> None:
    flag_on(owner)
    admin = make_user("admin", email="admin@example.com")
    fresh = new_client(app)
    first = login(fresh, admin.email)
    assert first.status_code == 202 and first.json()["step"] == "setup"
    assert fresh.get("/api/v1/auth/me").status_code == 401
    # The verify step isn't open for a set-up challenge.
    assert fresh.post(f"{TWO_FA}/verify", json={"code": "123456"}).status_code == 401
    setup = fresh.post(f"{TWO_FA}/enrol").json()
    secret = key_of(setup)
    assert fresh.post(f"{TWO_FA}/enrol/confirm", json={"code": "000000"}).status_code == 401
    done = fresh.post(f"{TWO_FA}/enrol/confirm", json={"code": code(secret, clock)})
    assert done.status_code == 200, done.text
    assert len(done.json()["recovery_codes"]) == 10
    assert done.json()["me"]["two_factor_enabled"] is True
    assert fresh.get("/api/v1/auth/me").status_code == 200


def test_with_the_flag_on_sales_still_sign_in_with_a_password(
    app: FastAPI, owner: SignedIn
) -> None:
    flag_on(owner)
    sales = make_user("sales", email="sales@example.com")
    assert login(new_client(app), sales.email).status_code == 200


def test_enrolment_start_makes_a_new_key_each_time(
    app: FastAPI, owner: SignedIn, clock: Clock
) -> None:
    flag_on(owner)
    admin = make_user("admin", email="admin@example.com")
    fresh = new_client(app)
    login(fresh, admin.email)
    old = key_of(fresh.post(f"{TWO_FA}/enrol").json())
    new = key_of(fresh.post(f"{TWO_FA}/enrol").json())
    assert old != new
    assert fresh.post(f"{TWO_FA}/enrol/confirm", json={"code": code(old, clock)}).status_code == 401
    assert fresh.post(f"{TWO_FA}/enrol/confirm", json={"code": code(new, clock)}).status_code == 200


def test_with_the_flag_off_nobody_without_two_factor_is_asked(
    app: FastAPI, owner: SignedIn
) -> None:
    admin = make_user("admin", email="admin@example.com")
    assert login(new_client(app), admin.email).status_code == 200


# --- Turning it off, new codes, the super-admin's reset ------------------------------------


def test_turning_it_off_needs_the_password_and_a_code(
    owner: SignedIn, clock: Clock, db: Session
) -> None:
    enrolled = turn_on(owner, clock)
    h = owner.headers()
    no_code = owner.client.post(
        f"{TWO_FA}/disable", json={"current_password": GOOD_PASSWORD}, headers=h
    )
    assert no_code.status_code == 422
    wrong_pw = owner.client.post(
        f"{TWO_FA}/disable",
        json={"current_password": "wrong password!!", "code": code(enrolled.secret, clock)},
        headers=h,
    )
    assert wrong_pw.status_code == 400
    wrong_code = owner.client.post(
        f"{TWO_FA}/disable", json={"current_password": GOOD_PASSWORD, "code": "000000"}, headers=h
    )
    assert wrong_code.status_code == 400 and wrong_code.json()["errors"][0]["field"] == "code"
    off = owner.client.post(
        f"{TWO_FA}/disable",
        json={"current_password": GOOD_PASSWORD, "code": code(enrolled.secret, clock)},
        headers=h,
    )
    assert off.status_code == 204
    assert db.get(UserTwoFactor, owner.user.id) is None
    assert db.scalars(select(TwoFactorRecoveryCode)).all() == []
    assert owner.client.get("/api/v1/auth/me").json()["two_factor_enabled"] is False


def test_new_recovery_codes_replace_the_old_ones(
    app: FastAPI, owner: SignedIn, clock: Clock
) -> None:
    enrolled = turn_on(owner, clock)
    r = owner.client.post(
        f"{TWO_FA}/recovery-codes",
        json={"recovery_code": enrolled.recovery_codes[0]},
        headers=owner.headers(),
    )
    assert r.status_code == 200
    fresh_codes = r.json()["recovery_codes"]
    assert len(fresh_codes) == 10 and not set(fresh_codes) & set(enrolled.recovery_codes)
    old = new_client(app)
    login(old, owner.user.email)
    assert (
        old.post(f"{TWO_FA}/verify", json={"recovery_code": enrolled.recovery_codes[1]}).status_code
        == 401
    )
    assert old.post(f"{TWO_FA}/verify", json={"recovery_code": fresh_codes[1]}).status_code == 200


def test_the_super_admin_resets_someones_two_factor(
    app: FastAPI, owner: SignedIn, clock: Clock, db: Session
) -> None:
    admin_user = make_user("admin", email="admin@example.com")
    admin = sign_in(new_client(app), admin_user)
    turn_on(admin, clock)
    r = owner.client.post(f"/api/v1/admin/users/{admin_user.id}/reset-2fa", headers=owner.headers())
    assert r.status_code == 204
    assert admin.client.get("/api/v1/auth/me").status_code == 401  # signed out everywhere
    assert db.get(UserTwoFactor, admin_user.id) is None
    row = db.scalars(select(AuditLog).where(AuditLog.action == "user.two_factor_reset")).one()
    assert row.actor_user_id == owner.user.id and row.changes == {
        "two_factor_enabled": [True, False]
    }
    assert "user.two_factor_reset" in [e.type for e in db.scalars(select(OutboxEvent))]
    assert login(new_client(app), admin_user.email).status_code == 200  # flag off: password only


def test_only_the_super_admin_resets_two_factor(app: FastAPI, owner: SignedIn) -> None:
    admin = sign_in(new_client(app), make_user("admin", email="admin@example.com"))
    r = admin.client.post(f"/api/v1/admin/users/{owner.user.id}/reset-2fa", headers=admin.headers())
    assert r.status_code == 403
    missing = owner.client.post(
        "/api/v1/admin/users/01a17441-0000-7000-8000-000000000000/reset-2fa",
        headers=owner.headers(),
    )
    assert missing.status_code == 404


# --- The flag rule ------------------------------------------------------------------------


def test_switching_the_flag_on_needs_your_own_two_factor(owner: SignedIn, clock: Clock) -> None:
    refused = owner.client.patch(
        f"{FLAGS}/admin_2fa", json={"enabled": True}, headers=owner.headers()
    )
    assert refused.status_code == 409
    listed = {f["key"]: f for f in owner.client.get(FLAGS).json()}["admin_2fa"]
    assert listed["can_switch"] is False and "your own account" in listed["cannot_switch_reason"]
    turn_on(owner, clock)
    allowed = owner.client.patch(
        f"{FLAGS}/admin_2fa", json={"enabled": True}, headers=owner.headers()
    )
    assert allowed.status_code == 200 and allowed.json()["enabled"] is True
    off = owner.client.patch(f"{FLAGS}/admin_2fa", json={"enabled": False}, headers=owner.headers())
    assert off.status_code == 200


def test_admins_can_not_switch_two_factor_even_with_their_own_on(
    app: FastAPI, clock: Clock
) -> None:
    admin = sign_in(new_client(app), make_user("admin", email="admin@example.com"))
    turn_on(admin, clock)
    r = admin.client.patch(f"{FLAGS}/admin_2fa", json={"enabled": True}, headers=admin.headers())
    assert r.status_code == 403
    listed = {f["key"]: f for f in admin.client.get(FLAGS).json()}["admin_2fa"]
    assert listed["can_switch"] is False


# --- Secrets never leak -------------------------------------------------------------------


def test_secrets_codes_and_tokens_never_reach_logs_audit_or_events(
    app: FastAPI, owner: SignedIn, clock: Clock, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    with captured_logs(monkeypatch) as logs:
        enrolled = turn_on(owner, clock)
        fresh = new_client(app)
        login(fresh, owner.user.email)
        token = fresh.cookies.get("__Host-empire_2fa") or ""
        used = code(enrolled.secret, clock)
        fresh.post(f"{TWO_FA}/verify", json={"code": used})
    secrets_ = [enrolled.secret, token, used, *enrolled.recovery_codes]
    dumped = repr(logs)
    with get_engine().connect() as conn:
        audit = repr(conn.execute(text("SELECT changes FROM audit_log")).all())
        events = repr(conn.execute(text("SELECT payload FROM outbox_event")).all())
        errors = repr(conn.execute(text("SELECT last_error FROM outbox_event")).all())
    for secret in secrets_:
        for where in (dumped, audit, events, errors):
            assert secret not in where
            assert secret.replace("-", "") not in where


def test_the_flag_switch_needs_the_csrf_token(owner: SignedIn) -> None:
    assert owner.client.patch(f"{FLAGS}/admin_2fa", json={"enabled": True}).status_code == 403


def test_an_unreadable_secret_says_so(
    owner: SignedIn, clock: Clock, db: Session, app: FastAPI
) -> None:
    turn_on(owner, clock)
    db.execute(text("UPDATE user_two_factor SET secret_encrypted = 'not-a-fernet-token'"))
    db.commit()
    fresh = new_client(app)
    login(fresh, owner.user.email)
    r = fresh.post(f"{TWO_FA}/verify", json={"code": "123456"})
    assert r.status_code == 409


def test_cleanup_removes_old_challenges(
    owner: SignedIn, clock: Clock, app: FastAPI, db: Session
) -> None:
    turn_on(owner, clock)
    login(new_client(app), owner.user.email)
    db.execute(text("UPDATE sign_in_challenge SET expires_at = now() - interval '2 days'"))
    db.commit()
    assert cleanup()["sign_in_challenges"] == 1


def test_deactivated_accounts_can_not_finish_the_second_step(
    app: FastAPI, owner: SignedIn, clock: Clock, db: Session
) -> None:
    admin_user = make_user("admin", email="admin@example.com")
    admin = sign_in(new_client(app), admin_user)
    enrolled = turn_on(admin, clock)
    fresh = new_client(app)
    login(fresh, admin_user.email)
    row = db.get(User, admin_user.id)
    assert row is not None
    row.is_active = False
    db.commit()
    r = fresh.post(f"{TWO_FA}/verify", json={"code": code(enrolled.secret, clock)})
    assert r.status_code == 401


def test_the_break_glass_cli_resets_two_factor(
    app: FastAPI, owner: SignedIn, clock: Clock, db: Session
) -> None:
    turn_on(owner, clock)
    result = CliRunner().invoke(cli_app, ["reset-two-factor", "--email", owner.user.email])
    assert result.exit_code == 0, result.output
    assert owner.client.get("/api/v1/auth/me").status_code == 401
    assert db.get(UserTwoFactor, owner.user.id) is None
    row = db.scalars(select(AuditLog).where(AuditLog.action == "user.two_factor_reset")).one()
    assert row.actor_user_id is None
    assert login(new_client(app), owner.user.email).status_code == 200
    missing = CliRunner().invoke(cli_app, ["reset-two-factor", "--email", "nobody@example.com"])
    assert missing.exit_code == 1


def test_two_confirmations_at_once_leave_one_set_of_recovery_codes(
    app: FastAPI, owner: SignedIn, clock: Clock, db: Session
) -> None:
    started = owner.client.post(
        f"{TWO_FA}/setup", json={"current_password": GOOD_PASSWORD}, headers=owner.headers()
    )
    secret = key_of(started.json())
    right = code(secret, clock)
    second = sign_in(new_client(app), owner.user)

    def confirm(signed: SignedIn) -> int:
        r = signed.client.post(
            f"{TWO_FA}/setup/confirm", json={"code": right}, headers=signed.headers()
        )
        return r.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(confirm, [owner, second]))
    assert statuses[0] == 200 and statuses[1] in (200, 401, 409)
    assert len(db.scalars(select(TwoFactorRecoveryCode)).all()) == 10
