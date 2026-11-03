"""Redirect hit counting (task 5.6, D-047): the website's redirect proxy reports each redirect it
answers, and `redirect.hits` / `last_hit_at` go up by one.

Collaborators: integrations/routes.py (`POST /api/v1/internal/redirects/hit`), the web app's
`apps/web/src/lib/public/redirects.ts` (the sender), seo/models.py (the columns).

SECURITY:
  - Only the web server can report a hit. The request is signed with REVALIDATE_SECRET, which
    the API and the web host already share (ARCHITECTURE §5), over
    `redirect-hit.{timestamp_ms}.{body}`. The prefix keeps a hit signature from ever being a valid
    revalidation signature, and the other way round.
  - A timestamp older or newer than five minutes is refused. A replayed hit within that window
    would count twice; counts are for staff insight only, so no replay cache is kept.
  - The path under /api/v1/internal/ is never reachable through the website (proxy.ts), and the
    answer is the same 204 whether or not the address has a redirect, so it reveals nothing.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Final

from sqlalchemy import update
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.platform.crypto import constant_time_equals
from empire_api.seo.models import Redirect
from empire_api.timeutil import utcnow

SIGNATURE_HEADER: Final = "x-redirect-hit-signature"
TIMESTAMP_HEADER: Final = "x-redirect-hit-timestamp"
MAX_SKEW_MS: Final = 5 * 60 * 1000
_PREFIX: Final = b"redirect-hit."


def hit_signature(secret: str, timestamp_ms: int, body: bytes) -> str:
    """HMAC-SHA256 hex over `redirect-hit.{timestamp_ms}.{body}`."""
    message = _PREFIX + f"{timestamp_ms}.".encode() + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def signature_ok(
    signature: str | None, timestamp: str | None, body: bytes, *, now_ms: int | None = None
) -> bool:
    if not signature or not timestamp or not timestamp.isdigit():
        return False
    ts = int(timestamp)
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    if abs(now - ts) > MAX_SKEW_MS:
        return False
    secret = get_settings().revalidate_secret.get_secret_value()
    return constant_time_equals(signature.lower(), hit_signature(secret, ts, body))


def record_hit(db: Session, from_path: str) -> None:
    """One more hit on the active redirect from `from_path`; nothing when there is none.

    PERF: one UPDATE, no read first; concurrent hits add up correctly (`hits = hits + 1`).
    """
    db.execute(
        update(Redirect)
        .where(Redirect.from_path == from_path, Redirect.is_active.is_(True))
        .values(hits=Redirect.hits + 1, last_hit_at=utcnow())
    )
    db.commit()
