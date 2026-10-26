"""What Settings and the dashboard show about email: which transport is active, and how many
emails couldn't be sent. Never the key.

Collaborators: site_settings/routes.py (the read-only `integrations` block), dashboard/service.py
("Needs attention"), config.py (transport), mail/handlers.py (which events send email).
COMPLIANCE: counts only, no personal data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Final, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.mail.events import EMAIL_EVENT_TYPES
from empire_api.platform.models import OutboxEvent
from empire_api.timeutil import utcnow

FAILED_WINDOW: Final = timedelta(days=7)
EmailStatus = Literal["connected", "not_configured", "dev"]


@dataclass(frozen=True)
class EmailTransportStatus:
    transport: Literal["resend", "dev"]
    status: EmailStatus
    from_address: str | None
    failed_last_7_days: int


def failed_emails(db: Session) -> int:
    """Events of an email-sending type that went dead in the last 7 days (mail/events.py).

    WHY these event types: only the email handlers can fail them (the other consumer is the
    log line). If a later phase adds another consumer to one of these types, give email its own
    delivery record instead of counting dead events.
    """
    return int(
        db.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(
                OutboxEvent.status == "dead",
                OutboxEvent.type.in_(EMAIL_EVENT_TYPES),
                OutboxEvent.occurred_at >= utcnow() - FAILED_WINDOW,
            )
        )
        or 0
    )


def transport_status(db: Session) -> EmailTransportStatus:
    settings = get_settings()
    kind = settings.email_transport_kind
    sender = settings.email_from.strip() or None
    if kind == "dev":
        status: EmailStatus = "dev"
    elif settings.email_api_key.get_secret_value().strip() and sender:
        status = "connected"
    else:
        status = "not_configured"
    return EmailTransportStatus(
        transport=kind, status=status, from_address=sender, failed_last_7_days=failed_emails(db)
    )
