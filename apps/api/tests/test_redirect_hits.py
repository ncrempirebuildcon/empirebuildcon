"""Redirect hits (task 5.6, D-047): the web server's signed report adds one hit to an active
redirect; unsigned, wrongly signed, stale or prefix-less (revalidation-style) reports are
refused; an unknown or inactive address changes nothing and gets the same 204."""

from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import SignedIn
from content_support import create_redirect
from empire_api.config import get_settings
from empire_api.integrations.revalidation import compute_signature
from empire_api.seo import hits
from empire_api.seo.models import Redirect

URL = "/api/v1/internal/redirects/hit"


def _post(client: TestClient, from_path: str, *, ts: int | None = None, sig: str | None = None):
    body = json.dumps({"from_path": from_path}).encode()
    ts = ts if ts is not None else int(time.time() * 1000)
    secret = get_settings().revalidate_secret.get_secret_value()
    sig = sig if sig is not None else hits.hit_signature(secret, ts, body)
    return client.post(
        URL,
        content=body,
        headers={
            "content-type": "application/json",
            hits.SIGNATURE_HEADER: sig,
            hits.TIMESTAMP_HEADER: str(ts),
        },
    )


def _row(db: Session, from_path: str) -> Redirect:
    db.expire_all()
    row = db.scalars(select(Redirect).where(Redirect.from_path == from_path)).one()
    return row


def test_a_signed_hit_counts_once(client: TestClient, owner: SignedIn, db: Session) -> None:
    create_redirect(owner, "/old-offer", "/contact")
    assert _post(client, "/old-offer").status_code == 204
    assert _post(client, "/old-offer").status_code == 204
    row = _row(db, "/old-offer")
    assert row.hits == 2
    assert row.last_hit_at is not None


def test_unsigned_wrong_stale_or_revalidation_signatures_are_refused(
    client: TestClient, owner: SignedIn, db: Session
) -> None:
    create_redirect(owner, "/old-brochure", "/projects")
    assert client.post(URL, json={"from_path": "/old-brochure"}).status_code == 401
    assert _post(client, "/old-brochure", sig="0" * 64).status_code == 401
    stale = int(time.time() * 1000) - hits.MAX_SKEW_MS - 1000
    assert _post(client, "/old-brochure", ts=stale).status_code == 401
    # A revalidation signature (no "redirect-hit." prefix) is not a hit signature.
    ts = int(time.time() * 1000)
    body = json.dumps({"from_path": "/old-brochure"}).encode()
    reval = compute_signature(get_settings().revalidate_secret.get_secret_value(), ts, body)
    assert _post(client, "/old-brochure", ts=ts, sig=reval).status_code == 401
    assert _row(db, "/old-brochure").hits == 0


def test_unknown_and_inactive_addresses_change_nothing(
    client: TestClient, owner: SignedIn, db: Session
) -> None:
    made = create_redirect(owner, "/old-tower", "/projects").json()
    off = owner.client.patch(
        f"/api/v1/admin/redirects/{made['id']}", json={"is_active": False}, headers=owner.headers()
    )
    assert off.status_code == 200, off.text
    assert _post(client, "/old-tower").status_code == 204
    assert _post(client, "/no-such-redirect").status_code == 204
    assert _row(db, "/old-tower").hits == 0


def test_a_bad_body_is_a_422(client: TestClient) -> None:
    ts = int(time.time() * 1000)
    body = b'{"nope": 1}'
    sig = hits.hit_signature(get_settings().revalidate_secret.get_secret_value(), ts, body)
    response = client.post(
        URL, content=body, headers={hits.SIGNATURE_HEADER: sig, hits.TIMESTAMP_HEADER: str(ts)}
    )
    assert response.status_code == 422


def test_the_signature_matches_the_web_apps_shared_vector() -> None:
    """Same vector as apps/web/test/redirects.test.ts (SHARED_VECTOR), so the two never drift."""
    body = b'{"from_path":"/old-offer"}'
    assert (
        hits.hit_signature("shared-test-secret", 1700000000000, body)
        == "84c44ffcdc10e4cd77cb2e6f291ae9a3e482b9bfa0ddad80a262a16449456afb"
    )


def test_odd_timestamps_and_large_bodies_are_refused_without_a_500(client: TestClient) -> None:
    ts = str(int(time.time() * 1000))
    for odd in ["\u00b2" * 3, "9" * 5000, "-1", ""]:
        response = client.post(
            URL,
            content=b"{}",
            headers={hits.SIGNATURE_HEADER: "0" * 64, hits.TIMESTAMP_HEADER: odd.encode("utf-8")},
        )
        assert response.status_code == 401, odd[:10]
    big = b'{"from_path":"/' + b"a" * 5000 + b'"}'
    response = client.post(
        URL, content=big, headers={hits.SIGNATURE_HEADER: "0" * 64, hits.TIMESTAMP_HEADER: ts}
    )
    assert response.status_code == 413
