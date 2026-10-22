"""Outbox handlers of the media module: destroy files at the store once the library no longer
needs them (`media.removed`) or an upload was never saved (`media.upload_discarded`).

Collaborators: integrations/outbox_drain.py imports this module so the handlers register;
store.py does the work.
Implements: ARCHITECTURE §9 (delivered with the outbox's retries: 1 min … 24 h, then dead).

INVARIANT: idempotent. Destroying a file that is already gone is not an error, so a retry after
a crash between "destroyed" and "marked delivered" is harmless.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from empire_api.integrations.handlers import on
from empire_api.logs import get_logger
from empire_api.media.store import get_store
from empire_api.media.vocab import RESOURCE_TYPES
from empire_api.platform.models import OutboxEvent

log = get_logger(__name__)


@on("media.removed")
@on("media.upload_discarded")
def destroy_at_store(db: Session, event: OutboxEvent) -> None:
    """Destroy the event's file at the store. A store error is raised, so the drain retries."""
    payload = event.payload
    store = get_store()
    if payload.get("store") != store.name:
        # WHY skip rather than fail: an event from the other store (say, a fake upload made
        # before CLOUDINARY_URL was set locally) can never be destroyed by this one.
        log.warning(
            "media_destroy_skipped", event_id=str(event.event_id), store=payload.get("store")
        )
        return
    public_id = str(payload["public_id"])
    if event.type == "media.upload_discarded":
        # SECURITY: the resource type in a direct-upload URL isn't signed, so the browser could
        # have stored the file as image, video or raw; destroy is idempotent, so try all three.
        for resource_type in RESOURCE_TYPES:
            store.destroy(resource_type, public_id)
    else:
        store.destroy(str(payload["resource_type"]), public_id)
    log.info("media_destroyed", event_id=str(event.event_id), public_id=public_id)
