"""Structured JSON logging with a request id on every line (ARCHITECTURE §20).

Collaborators: middleware/request_context.py binds `request_id`, `method`, `path`;
users/deps.py binds `user_id` once a session is verified.

SECURITY: never log passwords, tokens, form bodies or full phone numbers (SECURITY.md §8).
Use `mask_phone()` and log ids instead of names or emails.
"""

from __future__ import annotations

import logging
import sys
import traceback
from collections.abc import MutableMapping
from typing import Any

import structlog

_configured = False


def _exception_without_message(
    _logger: Any, _name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Replaces `exc_info` with the exception's type and stack, without its message.

    SECURITY (L2 security review): an exception message can quote stored values (a database
    error lists the row it failed on, a validation error the input), so a log line would carry a
    lead's phone or name. The type and where it happened are enough to debug.
    """
    exc_info = event_dict.pop("exc_info", None)
    if not exc_info:
        return event_dict
    if exc_info is True:
        exc_info = sys.exc_info()
    elif isinstance(exc_info, BaseException):
        exc_info = (type(exc_info), exc_info, exc_info.__traceback__)
    if not isinstance(exc_info, tuple) or exc_info[0] is None:
        return event_dict
    event_dict["exception"] = format_without_messages(exc_info[1])
    return event_dict


def format_without_messages(exc: BaseException | None) -> str:
    """Each exception in the chain (cause or context first) as its stack and its type only."""
    parts: list[str] = []
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        stack = "".join(traceback.format_tb(exc.__traceback__)) if exc.__traceback__ else ""
        parts.append(f"{stack}{type(exc).__module__}.{type(exc).__qualname__}")
        exc = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
    return "\n-- then --\n".join(reversed(parts))


class _NoMessageFormatter(logging.Formatter):
    """For stdlib loggers (uvicorn, SQLAlchemy, httpx): a traceback without exception messages,
    for the same reason as `_exception_without_message`."""

    def formatException(self, ei: Any) -> str:  # noqa: N802 — the stdlib's name
        return format_without_messages(ei[1] if ei else None)


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog + stdlib logging once per process. Safe to call repeatedly."""
    global _configured  # noqa: PLW0603 — process-wide, one-time setup
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_NoMessageFormatter("%(message)s"))
    logging.basicConfig(handlers=[handler], level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _exception_without_message,
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
