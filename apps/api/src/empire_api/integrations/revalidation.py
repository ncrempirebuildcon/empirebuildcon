"""Web revalidation integration: maps publish events to Next.js cache tags and calls
the web app's signed /_internal/revalidate route (ARCHITECTURE §5, §9).

SECURITY:
  - Calls carry an HMAC-SHA256 signature over timestamp + body with REVALIDATE_SECRET.
  - No personal data is sent in the call (only cache tag strings).
  - Outbox retries on transient errors; fails loud on misconfiguration in staging/prod.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Sequence
from typing import Any, Final

import httpx
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.content.models import Page, Post
from empire_api.logs import get_logger
from empire_api.media.usage import usage
from empire_api.platform.models import OutboxEvent
from empire_api.projects.models import Project

log = get_logger(__name__)

REVALIDATION_EVENTS: Final[frozenset[str]] = frozenset(
    {
        "project.published",
        "project.updated",
        "project.unpublished",
        "configuration.changed",
        "construction_update.published",
        "media.added",
        "media.updated",
        "media.removed",
        "page.published",
        "page.unpublished",
        "page.updated",
        "post.published",
        "post.unpublished",
        "post.updated",
        "faq.changed",
        "testimonial.changed",
        "offer.started",
        "offer.ended",
        "offer.changed",
        "settings.updated",
        "flag.changed",
        "redirect.changed",
        "consent_text.published",
    }
)

SIGNATURE_HEADER: Final = "x-empire-signature"
TIMESTAMP_HEADER: Final = "x-empire-timestamp"


def compute_signature(secret: str, timestamp_ms: int, body_bytes: bytes) -> str:
    """HMAC-SHA256 hex digest over `{timestamp_ms}.{body_bytes}` using secret."""
    message = f"{timestamp_ms}.".encode() + body_bytes
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _project_tags(db: Session, event: OutboxEvent, payload: dict[str, Any]) -> set[str]:
    tags: set[str] = {"projects", "properties", "site"}
    slug = payload.get("slug")
    if slug:
        tags.add(f"project:{slug}")
    prev_slug = payload.get("previous_slug")
    if prev_slug:
        tags.add(f"project:{prev_slug}")
    if not slug and event.aggregate_type == "project":
        with db.no_autoflush:
            try:
                p = db.get(Project, uuid.UUID(event.aggregate_id))
                if p:
                    tags.add(f"project:{p.slug}")
            except ValueError, TypeError:
                pass
    return tags


def _page_tags(db: Session, event: OutboxEvent, payload: dict[str, Any]) -> set[str]:
    tags = {"site"}
    slug = payload.get("slug")
    if slug:
        tags.add(f"page:{slug}")
    elif event.aggregate_type == "page":
        with db.no_autoflush:
            try:
                page = db.get(Page, uuid.UUID(event.aggregate_id))
                if page:
                    tags.add(f"page:{page.slug}")
            except ValueError, TypeError:
                pass
    return tags


def _post_tags(db: Session, event: OutboxEvent, payload: dict[str, Any]) -> set[str]:
    tags = {"posts"}
    slug = payload.get("slug")
    if slug:
        tags.add(f"post:{slug}")
    elif event.aggregate_type == "post":
        with db.no_autoflush:
            try:
                post = db.get(Post, uuid.UUID(event.aggregate_id))
                if post:
                    tags.add(f"post:{post.slug}")
            except ValueError, TypeError:
                pass
    return tags


def _content_tags(db: Session, event: OutboxEvent, payload: dict[str, Any]) -> set[str]:
    event_type = event.type
    if event_type in ("page.published", "page.unpublished", "page.updated"):
        return _page_tags(db, event, payload)
    if event_type in ("post.published", "post.unpublished", "post.updated"):
        return _post_tags(db, event, payload)
    if event_type == "faq.changed":
        return {"faqs", "site"}
    if event_type == "testimonial.changed":
        return {"testimonials", "site"}
    if event_type == "redirect.changed":
        return {"redirects", "site"}
    return {"site"}


def _media_tags(db: Session, event: OutboxEvent, payload: dict[str, Any]) -> set[str]:
    tags: set[str] = set()
    slug = payload.get("slug")
    if slug:
        tags.update(["projects", f"project:{slug}"])

    media_id_str = payload.get("media_id") or (
        event.aggregate_id if event.aggregate_type == "media" else None
    )
    if not media_id_str:
        return tags

    with db.no_autoflush:
        try:
            m_uuid = uuid.UUID(media_id_str)
            uses = usage(db, m_uuid)
            for u in uses:
                if u.owner_type == "project" and u.project_id:
                    p = db.get(Project, u.project_id)
                    if p and p.publish_state == "published":
                        tags.update(["projects", f"project:{p.slug}"])
                elif u.owner_type == "page":
                    page = db.get(Page, u.owner_id)
                    if page and page.publish_state == "published":
                        tags.update(["site", f"page:{page.slug}"])
                elif u.owner_type == "post":
                    post = db.get(Post, u.owner_id)
                    if post and post.publish_state == "published":
                        tags.update(["posts", f"post:{post.slug}"])
                elif u.owner_type in ("testimonial", "offer"):
                    tags.update(["site", "testimonials"])
        except ValueError, TypeError:
            pass
    return tags


def tags_for_event(db: Session, event: OutboxEvent) -> list[str]:
    """Map an outbox event to Next.js cache tags that should be cleared."""
    event_type = event.type
    payload = event.payload or {}

    if event_type in ("project.published", "project.updated", "project.unpublished"):
        return sorted(_project_tags(db, event, payload))

    if event_type == "configuration.changed":
        tags = {"properties"}
        slug = payload.get("slug")
        if slug:
            tags.add(f"project:{slug}")
        elif event.aggregate_type == "configuration":
            tags.add("projects")
        return sorted(tags)

    if event_type == "construction_update.published":
        slug = payload.get("slug")
        return [f"project:{slug}"] if slug else []

    if event_type in ("media.added", "media.updated", "media.removed"):
        return sorted(_media_tags(db, event, payload))

    return sorted(_content_tags(db, event, payload))


def send_revalidation(
    tags: Sequence[str],
    *,
    url: str | None = None,
    secret: str | None = None,
    client: httpx.Client | None = None,
) -> None:
    """Send signed revalidation request to the web app for given tags.

    Raises on HTTP or network error so the outbox handler can retry.
    """
    if not tags:
        return

    st = get_settings()
    target_url = (url or st.web_revalidate_url).strip()
    sec = secret or st.revalidate_secret.get_secret_value()

    if not target_url:
        log.debug("revalidation_skipped_no_url", tags=tags)
        return

    now_ms = int(time.time() * 1000)
    body_payload = {"tags": sorted(set(tags))}
    body_bytes = json.dumps(body_payload, separators=(",", ":")).encode()
    sig = compute_signature(sec, now_ms, body_bytes)

    headers = {
        "Content-Type": "application/json",
        SIGNATURE_HEADER: sig,
        TIMESTAMP_HEADER: str(now_ms),
    }

    if client is not None:
        resp = client.post(target_url, content=body_bytes, headers=headers)
        resp.raise_for_status()
    else:
        with httpx.Client(timeout=5.0) as http:
            resp = http.post(target_url, content=body_bytes, headers=headers)
            resp.raise_for_status()

    log.info("revalidation_sent", tags=tags, status_code=resp.status_code)


def handle_revalidation(db: Session, event: OutboxEvent) -> None:
    """Outbox handler for publish and content events."""
    tags = tags_for_event(db, event)
    if tags:
        send_revalidation(tags)
