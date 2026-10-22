"""Structured JSON logging with a request id on every line (ARCHITECTURE §20).

Collaborators: middleware/request_context.py binds `request_id`, `method`, `path`;
users/deps.py binds `user_id` once a session is verified.

SECURITY: never log passwords, tokens, form bodies or full phone numbers (SECURITY.md §8).
Use `mask_phone()` and log ids instead of names or emails.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog + stdlib logging once per process. Safe to call repeatedly."""
    global _configured  # noqa: PLW0603 — process-wide, one-time setup
    if _configured:
        return
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str | None = None, **initial: Any) -> Any:
    """A bound structlog logger. Typed `Any` because structlog's bound loggers are dynamic."""
    return structlog.get_logger(name, **initial)


def mask_phone(phone: str | None) -> str:
    """Mask a phone number for logs: '+919876543210' → '+91 98xxxxxx10'.

    Keeps the country code, the first two and last two digits, so support staff can still
    match a log line to a lead they already have open, but a log reader learns nothing new.
    """
    if not phone:
        return ""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 6:
        return "x" * len(digits)
    if phone.strip().startswith("+") and digits.startswith("91") and len(digits) == 12:
        local = digits[2:]
        return f"+91 {local[:2]}{'x' * (len(local) - 4)}{local[-2:]}"
    return f"{digits[:2]}{'x' * (len(digits) - 4)}{digits[-2:]}"
