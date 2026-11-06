"""The outbox event types that send email (mail/handlers.py registers a handler for each;
tests/test_mail_handlers.py checks the two lists match). The dashboard counts dead events of
these types as "emails that couldn't be sent" (mail/status.py)."""

from __future__ import annotations

from typing import Final

PASSWORD_LINK_EVENTS: Final = ("user.setup_link_issued", "user.password_reset_requested")
SECURITY_NOTICE_EVENTS: Final = (
    "user.locked",
    "user.password_changed",
    "user.two_factor_enabled",
    "user.two_factor_disabled",
    "user.two_factor_reset",
    "user.recovery_code_used",
)
LEAD_EVENTS: Final = ("lead.created", "lead.assigned", "site_visit.requested")
# Super-admin changes, announced to every super-admin (L2 security review).
ADMIN_CHANGE_EVENTS: Final = ("user.created", "user.updated")
EMAIL_EVENT_TYPES: Final = (
    *PASSWORD_LINK_EVENTS,
    *SECURITY_NOTICE_EVENTS,
    *LEAD_EVENTS,
    *ADMIN_CHANGE_EVENTS,
)
