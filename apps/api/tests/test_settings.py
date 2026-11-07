"""Settings groups (/admin/settings, /admin/settings/{group}): the typed overview, who may change
each group (settings.write, marketing.tracking, seo.manage, super-admin for retention), the field
rules, the fixed RERA fields (COMPLIANCE), lead-routing checks, audit and events, and an
integrations block that never shows a key."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import SignedIn, make_user
from empire_api.config import Settings, get_settings
from empire_api.db import get_sessionmaker
from empire_api.leads.erasure import retention_years
from empire_api.mail.status import transport_status
from empire_api.platform.models import AuditLog, OutboxEvent
from empire_api.site_settings.fields import gstin_check_character
from empire_api.site_settings.models import Setting
from leads_support import enquiry, lead_by_reference, staff_client, submit_ok

SETTINGS = "/api/v1/admin/settings"


def patch(signed: SignedIn, group: str, body: dict[str, Any]) -> Any:
    return signed.client.patch(f"{SETTINGS}/{group}", json=body, headers=signed.headers())


def field_errors(response: Any) -> dict[str, str]:
    assert response.status_code == 422, response.text
    return {e["field"]: e["message"] for e in response.json()["errors"]}


# --- Reading -------------------------------------------------------------------------------


def test_the_overview_lists_every_group_with_who_can_change_it(owner: SignedIn) -> None:
    body = owner.client.get(SETTINGS).json()
    for group in (
        "company", "contacts", "social", "tracking", "lead_routing", "seo_defaults",
        "regulator", "email", "privacy",
    ):  # fmt: skip
        assert group in body
    meta = {g["key"]: g for g in body["groups"]}
    assert meta["tracking"]["permission"] == "marketing.tracking"
    assert meta["seo_defaults"]["permission"] == "seo.manage"
    assert meta["privacy"]["super_admin_only"] is True
    assert all(g["can_edit"] for g in body["groups"])
    assert body["company"]["legal_name"] == "[Company legal name]"
    assert body["privacy"]["lead_retention_years"] == 3
    assert body["regulator"]["show_rera_everywhere"] is True
    assert body["regulator"]["state_name"] == "Uttar Pradesh"


def test_marketing_reads_but_sales_can_not(app: FastAPI) -> None:
    marketing = staff_client(app, "marketing")
    body = marketing.client.get(SETTINGS).json()
    meta = {g["key"]: g["can_edit"] for g in body["groups"]}
    assert meta == {
        "company": False, "contacts": False, "social": False, "tracking": True,
        "lead_routing": False, "seo_defaults": True, "regulator": False, "email": False,
        "privacy": False,
    }  # fmt: skip
    assert staff_client(app, "sales").client.get(SETTINGS).status_code == 403


def test_the_integrations_block_never_shows_the_key(
    owner: SignedIn, monkeypatch: pytest.MonkeyPatch
) -> None:
    block = owner.client.get(SETTINGS).json()["integrations"]
    assert block["email"] == {
        "transport": "dev", "status": "dev", "from_address": None, "failed_last_7_days": 0,
    }  # fmt: skip
    assert block["crm"]["status"] == "none" and block["webhooks"]["status"] == "phase_6"
    secret = "re_not_a_real_key_but_secret_looking"
    monkeypatch.setenv("EMAIL_API_KEY", secret)
    monkeypatch.setenv("EMAIL_FROM", "alerts@example.com")
    get_settings.cache_clear()
    try:
        response = owner.client.get(SETTINGS)
    finally:
        monkeypatch.delenv("EMAIL_API_KEY")
        monkeypatch.delenv("EMAIL_FROM")
        get_settings.cache_clear()
    email = response.json()["integrations"]["email"]
    assert email["status"] == "connected" and email["from_address"] == "alerts@example.com"
    assert secret not in response.text


def test_resend_without_a_sender_is_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(**{**get_settings().model_dump(), "email_api_key": SecretStr("k" * 20)})
    assert settings.email_transport_kind == "resend"
    monkeypatch.setenv("EMAIL_API_KEY", "k" * 20)
    get_settings.cache_clear()
    try:
        with get_sessionmaker()() as db:
            assert transport_status(db).status == "not_configured"
    finally:
        monkeypatch.delenv("EMAIL_API_KEY")
        get_settings.cache_clear()


# --- Permissions ---------------------------------------------------------------------------


def test_tracking_needs_marketing_tracking_not_settings_write(
    app: FastAPI, owner: SignedIn
) -> None:
    marketing = staff_client(app, "marketing")
    ok = patch(marketing, "tracking", {"gtm_id": "gtm-ab12cd3"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["gtm_id"] == "GTM-AB12CD3"
    refused = patch(marketing, "company", {"tagline": "Homes"})
    assert refused.status_code == 403 and "settings.write" in refused.json()["detail"]
    editor = staff_client(app, "content_editor")
    assert patch(editor, "tracking", {"gtm_id": "GTM-AB12CD3"}).status_code == 403
    sales = staff_client(app, "sales")
    assert patch(sales, "tracking", {"gtm_id": "GTM-AB12CD3"}).status_code == 403


def test_seo_defaults_need_seo_manage(app: FastAPI) -> None:
    marketing = staff_client(app, "marketing")
    r = patch(marketing, "seo_defaults", {"default_title": "Homes in Noida"})
    assert r.status_code == 200 and r.json()["title_suffix"] == " · Empire"


def test_retention_needs_the_super_admin(app: FastAPI, owner: SignedIn, db: Session) -> None:
    """COMPLIANCE: privacy.lead_retention_years is on the owner-approval list."""
    admin = staff_client(app, "admin")
    refused = patch(admin, "privacy", {"lead_retention_years": 5})
    assert refused.status_code == 403 and "super-admin" in refused.json()["detail"]
    assert field_errors(patch(owner, "privacy", {"lead_retention_years": 11})) == {
        "lead_retention_years": "Input should be less than or equal to 10"
    }
    assert patch(owner, "privacy", {"lead_retention_years": 0}).status_code == 422
    ok = patch(owner, "privacy", {"lead_retention_years": 5})
    assert ok.status_code == 200 and ok.json() == {"lead_retention_years": 5}
    assert retention_years(db) == 5


def test_writes_need_csrf(owner: SignedIn) -> None:
    assert owner.client.patch(f"{SETTINGS}/company", json={"tagline": "x"}).status_code == 403


def test_unknown_group_is_422(owner: SignedIn) -> None:
    assert patch(owner, "secrets", {"x": 1}).status_code == 422


# --- Field rules ---------------------------------------------------------------------------


def test_gstin_format_and_check_character(owner: SignedIn) -> None:
    assert gstin_check_character("27AAPFU0939F1Z") == "V"
    ok = patch(owner, "company", {"gstin": "27aapfu0939f1zv"})
    assert ok.status_code == 200 and ok.json()["gstin"] == "27AAPFU0939F1ZV"
    assert (
        "last character"
        in field_errors(patch(owner, "company", {"gstin": "27AAPFU0939F1ZX"}))["gstin"]
    )
    assert "15-character" in field_errors(patch(owner, "company", {"gstin": "ABC"}))["gstin"]
    assert (
        "15-character"
        in field_errors(patch(owner, "company", {"gstin": "40AAPFU0939F1ZV"}))["gstin"]
    )
    cleared = patch(owner, "company", {"gstin": ""})
    assert cleared.status_code == 200 and cleared.json()["gstin"] is None


def test_phones_follow_the_leads_rule(owner: SignedIn) -> None:
    ok = patch(
        owner, "contacts", {"sales_phone": "098765 43210", "whatsapp_number": "+91-98765-43211"}
    )
    assert ok.status_code == 200
    assert ok.json()["sales_phone"] == "+919876543210"
    assert ok.json()["whatsapp_number"] == "+919876543211"
    errors = field_errors(
        patch(owner, "contacts", {"customer_care_phone": "12345", "sales_email": "not-an-email"})
    )
    assert set(errors) == {"customer_care_phone", "sales_email"}
    assert (
        "STD code" in errors["customer_care_phone"] or "10-digit" in errors["customer_care_phone"]
    )
    assert patch(owner, "contacts", {"sales_phone": "+44 20 7946 0000"}).status_code == 422


def test_the_whatsapp_message_allows_only_the_page_placeholder(owner: SignedIn) -> None:
    ok = patch(owner, "contacts", {"whatsapp_message": "Hi, I'm interested in {page}."})
    assert ok.status_code == 200
    assert (
        "{page}"
        in field_errors(patch(owner, "contacts", {"whatsapp_message": "Hi {name}"}))[
            "whatsapp_message"
        ]
    )
    assert patch(owner, "contacts", {"whatsapp_message": "<b>Hi</b>"}).status_code == 422


@pytest.mark.parametrize(
    ("network", "good", "bad"),
    [
        ("facebook", "https://www.facebook.com/empire", "https://facebook.com.evil.example/empire"),
        ("instagram", "https://instagram.com/empire", "http://instagram.com/empire"),
        ("youtube", "https://www.youtube.com/@empire", "javascript:alert(1)"),
        (
            "linkedin",
            "https://in.linkedin.com/company/empire",
            "https://user@linkedin.com/company/x",
        ),
    ],
)
def test_social_links_are_https_on_the_networks_own_hosts(
    owner: SignedIn, network: str, good: str, bad: str
) -> None:
    assert patch(owner, "social", {network: good}).status_code == 200
    assert network in field_errors(patch(owner, "social", {network: bad}))
    assert patch(owner, "social", {network: "https://www.facebook.com/"}).status_code == 422


def test_tracking_ids_have_their_formats(owner: SignedIn) -> None:
    ok = patch(
        owner,
        "tracking",
        {
            "ga4_id": "g-ab12cd34ef",
            "meta_pixel_id": "123456789012345",
            "google_ads_id": "aw-123456789",
        },
    )
    assert ok.status_code == 200 and ok.json()["ga4_id"] == "G-AB12CD34EF"
    errors = field_errors(
        patch(
            owner,
            "tracking",
            {"gtm_id": "UA-1234", "meta_pixel_id": "12ab", "google_ads_id": "AW-x"},
        )
    )
    assert set(errors) == {"gtm_id", "meta_pixel_id", "google_ads_id"}


def test_the_sender_name_can_not_inject_headers(owner: SignedIn) -> None:
    for name in ('Empire" <evil@example.com>', "Empire\r\nBcc: evil@example.com", "a@b"):
        assert patch(owner, "email", {"sender_name": name}).status_code == 422
    ok = patch(owner, "email", {"sender_name": "Empire Sales", "reply_to": "sales@example.com"})
    assert ok.status_code == 200


def test_no_html_in_company_texts(owner: SignedIn) -> None:
    assert "legal_name" in field_errors(
        patch(owner, "company", {"legal_name": "<script>x</script>"})
    )


def test_unknown_fields_are_refused(owner: SignedIn) -> None:
    errors = field_errors(patch(owner, "company", {"api_key": "x"}))
    assert errors == {"api_key": "This field isn't part of this settings group."}


# --- RERA (COMPLIANCE) ---------------------------------------------------------------------


def test_the_regulator_is_fixed_and_rera_always_shows(owner: SignedIn) -> None:
    errors = field_errors(
        patch(
            owner,
            "regulator",
            {
                "authority": "MahaRERA",
                "website": "https://maharera.mahaonline.gov.in",
                "show_rera_everywhere": False,
            },
        )
    )
    assert set(errors) == {"authority", "website", "show_rera_everywhere"}
    assert "can't be switched off" in errors["show_rera_everywhere"]
    ok = patch(
        owner, "regulator", {"promoter_registration_number": "uprera prm 1234", "state": "UP"}
    )
    assert ok.status_code == 200
    assert ok.json()["promoter_registration_number"] == "UPRERAPRM1234"
    assert ok.json()["locked_fields"] == ["state", "authority", "website", "show_rera_everywhere"]


# --- Lead routing --------------------------------------------------------------------------


def test_routing_names_only_people_who_can_own_leads(owner: SignedIn) -> None:
    sales = make_user("sales", email="sales1@example.com", name="Sales 1")
    marketing = make_user("marketing", email="marketing@example.com")
    gone = make_user("sales", email="gone@example.com", is_active=False)
    errors = field_errors(
        patch(
            owner,
            "lead_routing",
            {
                "mode": "round_robin",
                "round_robin_user_ids": [str(sales.id), str(marketing.id), str(gone.id)],
                "single_owner_user_id": str(marketing.id),
            },
        )
    )
    assert set(errors) == {
        "round_robin_user_ids.1",
        "round_robin_user_ids.2",
        "single_owner_user_id",
    }
    dup = field_errors(
        patch(owner, "lead_routing", {"round_robin_user_ids": [str(sales.id), str(sales.id)]})
    )
    assert "round_robin_user_ids" in dup
    paused = field_errors(
        patch(
            owner,
            "lead_routing",
            {
                "round_robin_user_ids": [str(sales.id)],
                "round_robin_paused_user_ids": [str(owner.user.id)],
            },
        )
    )
    assert "round_robin_paused_user_ids.0" in paused
    assert patch(owner, "lead_routing", {"mode": "everyone"}).status_code == 422


def test_the_round_robin_table_shows_the_rotation_and_who_is_next(
    owner: SignedIn, texts: dict[str, Any], intake_unlimited: None, client: Any
) -> None:
    one = make_user("sales", email="sales1@example.com", name="Sales 1")
    two = make_user("sales", email="sales2@example.com", name="Sales 2")
    three = make_user("sales", email="sales3@example.com", name="Sales 3")
    ids = [str(one.id), str(two.id), str(three.id)]
    r = patch(
        owner,
        "lead_routing",
        {
            "mode": "round_robin",
            "round_robin_user_ids": ids,
            "round_robin_paused_user_ids": [str(two.id)],
        },
    )
    assert r.status_code == 200, r.text
    rows = owner.client.get(SETTINGS).json()["lead_rotation"]
    assert [(row["user"]["name"], row["in_rotation"], row["gets_next"]) for row in rows] == [
        ("Sales 1", True, True), ("Sales 2", False, False), ("Sales 3", True, False),
    ]  # fmt: skip
    submit_ok(client, enquiry(texts, 1))
    rows = owner.client.get(SETTINGS).json()["lead_rotation"]
    assert [row["open_leads"] for row in rows] == [1, 0, 0]
    assert [row["gets_next"] for row in rows] == [False, False, True]  # Sales 2 is paused


def test_routing_skips_paused_people(
    owner: SignedIn, texts: dict[str, Any], intake_unlimited: None, client: Any, db: Session
) -> None:
    one = make_user("sales", email="sales1@example.com")
    two = make_user("sales", email="sales2@example.com")
    patch(
        owner,
        "lead_routing",
        {
            "mode": "round_robin",
            "round_robin_user_ids": [str(one.id), str(two.id)],
            "round_robin_paused_user_ids": [str(one.id)],
        },
    )
    owners = {
        lead_by_reference(db, submit_ok(client, enquiry(texts, n))).owner_user_id for n in (1, 2, 3)
    }
    assert owners == {two.id}


# --- Audit and events ----------------------------------------------------------------------


def test_every_change_is_audited_with_before_and_after(owner: SignedIn, db: Session) -> None:
    r = patch(
        owner,
        "contacts",
        {"office_hours": "Mon–Sat, 10:00–19:00", "sales_email": "sales@example.com"},
    )
    assert r.status_code == 200
    [row] = db.scalars(select(AuditLog).where(AuditLog.action == "settings.updated")).all()
    assert row.entity_id == "contacts" and row.actor_user_id == owner.user.id
    assert row.changes == {
        "office_hours": [None, "Mon–Sat, 10:00–19:00"],
        "sales_email": [None, "sales@example.com"],
    }
    [event] = db.scalars(select(OutboxEvent).where(OutboxEvent.type == "settings.updated")).all()
    assert event.payload == {"group": "contacts", "changed": ["office_hours", "sales_email"]}
    # Sending the same values again changes nothing and writes nothing.
    assert patch(owner, "contacts", {"office_hours": "Mon–Sat, 10:00–19:00"}).status_code == 200
    assert len(db.scalars(select(AuditLog).where(AuditLog.action == "settings.updated")).all()) == 1
    meta = {g["key"]: g for g in owner.client.get(SETTINGS).json()["groups"]}
    assert meta["contacts"]["updated_by"]["id"] == str(owner.user.id)


def test_partial_updates_keep_the_other_fields(owner: SignedIn) -> None:
    patch(owner, "company", {"legal_name": "Empire Test Pvt Ltd", "tagline": "Homes"})
    r = patch(owner, "company", {"tagline": None})
    assert r.json()["legal_name"] == "Empire Test Pvt Ltd" and r.json()["tagline"] is None


def test_old_keys_in_stored_rows_are_ignored(owner: SignedIn, db: Session) -> None:
    db.merge(Setting(key="contacts", value={"hours": "old", "whatsapp": "x", "sales_phone": "bad"}))
    db.commit()
    body = owner.client.get(SETTINGS).json()["contacts"]
    assert body["sales_phone"] is None and "hours" not in body
    assert patch(owner, "contacts", {"office_hours": "10–7"}).status_code == 200


def test_public_site_sends_tracking_ids_only_once_set(owner: SignedIn, client: Any) -> None:
    """Task 6.3 (D-058): no IDs → `tracking` is null (the launch state); IDs set → sent."""
    assert client.get("/api/v1/public/site").json()["tracking"] is None
    response = patch(
        owner, "tracking", {"ga4_id": "G-AB12CD34EF", "meta_pixel_id": "123456789012345"}
    )
    assert response.status_code == 200, response.text
    tracking = client.get("/api/v1/public/site").json()["tracking"]
    assert tracking == {
        "gtm_id": None,
        "ga4_id": "G-AB12CD34EF",
        "meta_pixel_id": "123456789012345",
        "google_ads_id": None,
    }
