"""Helpers for two-factor and email tests: a controllable clock for TOTP codes, turning two-factor
on through the API, and reading the dev mailbox.

`clock` (fixture below via `use_clock`): the two-factor module's "now", so a test can step past
the 30-second step whose code was already used (replays are refused within a step).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import GOOD_PASSWORD, SignedIn
from empire_api.integrations.outbox_drain import drain
from empire_api.mail.dev import DevMessage, DevTransport
from empire_api.users import totp, two_factor

TWO_FA = "/api/v1/auth/2fa"


@dataclass
class Clock:
    now: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __call__(self) -> datetime:
        return self.now

    def next_step(self) -> None:
        """Move to the next 30-second step, so a new code can be accepted."""
        self.now += timedelta(seconds=totp.PERIOD_SECONDS)


def use_clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(two_factor, "utcnow", clock)
    return clock


def key_of(setup: dict[str, Any]) -> str:
    return str(setup["secret"]).replace(" ", "")


def code(secret: str, clock: Clock) -> str:
    return totp.code_at(secret, clock.now)


@dataclass
class Enrolled:
    secret: str
    recovery_codes: list[str]


def turn_on(signed: SignedIn, clock: Clock, password: str = GOOD_PASSWORD) -> Enrolled:
    """My account: set two-factor up and confirm it. Moves the clock past the used step."""
    started = signed.client.post(
        f"{TWO_FA}/setup", json={"current_password": password}, headers=signed.headers()
    )
    assert started.status_code == 200, started.text
    secret = key_of(started.json())
    confirmed = signed.client.post(
        f"{TWO_FA}/setup/confirm", json={"code": code(secret, clock)}, headers=signed.headers()
    )
    assert confirmed.status_code == 200, confirmed.text
    clock.next_step()
    return Enrolled(secret=secret, recovery_codes=confirmed.json()["recovery_codes"])


def login(client: TestClient, email: str, password: str = GOOD_PASSWORD) -> Any:
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def mailbox() -> DevTransport:
    return DevTransport(Path(os.environ["MAIL_DEV_DIR"]))


def mail_to(address: str, template: str | None = None) -> list[DevMessage]:
    """Every dev-mailbox message to `address` (optionally one template), after a drain."""
    drain()
    return [
        m
        for m in mailbox().messages()
        if m.to == address.lower() and (template is None or m.template == template)
    ]


def all_mail() -> list[dict[str, Any]]:
    """Every stored message with its HTML, for "never in any email" scans."""
    drain()
    root = Path(os.environ["MAIL_DEV_DIR"])
    return [json.loads(p.read_text()) for p in sorted(root.glob("*.json"))] if root.is_dir() else []
