"""The dev mailbox: a transport that never sends (development, tests, the browser suite).

Collaborators: mail/transport.py (interface), mail/routes_dev.py (`GET /api/v1/dev-mail/latest`
reads the newest message to an address, so the browser suite can open a setup link).
Implements: the Phase 4 part 5 rule "no real email without a Resend key".

Each message is one JSON file in MAIL_DEV_DIR (default apps/api/.mail-dev/, git-ignored), named
after its idempotency key: sending the same key again keeps the first file, as Resend keeps the
first message for a repeated key.

SECURITY: these files hold setup and reset links in plain text, which is the point: they exist
only on a developer's machine or a CI runner. config.py refuses this transport in staging and
production, and main.py mounts the dev mailbox route only while it is active in development or
test. The folder is git-ignored.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from empire_api.config import Settings
from empire_api.mail.transport import OutgoingEmail, TransportName, from_header
from empire_api.timeutil import utcnow

API_ROOT: Final = Path(__file__).resolve().parents[3]
DEFAULT_DIR: Final = API_ROOT / ".mail-dev"


@dataclass(frozen=True)
class DevMessage:
    id: str
    to: str
    subject: str
    template: str
    links: tuple[str, ...]
    text: str
    sent_at: datetime


class DevTransport:
    name: TransportName = "dev"

    def __init__(self, root: Path) -> None:
        self.root = root

    @classmethod
    def from_settings(cls, settings: Settings) -> DevTransport:
        return cls(Path(settings.mail_dev_dir) if settings.mail_dev_dir else DEFAULT_DIR)

    def _path(self, idempotency_key: str) -> Path:
        # WHY hashed: the key is ours, but a file name should never depend on its characters.
        name = hashlib.sha256(idempotency_key.encode()).hexdigest()[:40]
        return self.root / f"{name}.json"

    def send(self, message: OutgoingEmail) -> str:
        path = self._path(message.idempotency_key)
        if path.exists():
            return path.stem
        self.root.mkdir(parents=True, exist_ok=True)
        record: dict[str, Any] = {
            "id": path.stem,
            "from": from_header(message.sender_name),
            "to": message.to,
            "reply_to": message.reply_to,
            "subject": message.subject,
            "template": message.template,
            "links": list(message.links),
            "text": message.text,
            "html": message.html,
            "sent_at": utcnow().isoformat(),
        }
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)  # WHY: a reader never sees half a file
        return path.stem

    def messages(self) -> list[DevMessage]:
        """Every stored message, oldest first."""
        if not self.root.is_dir():
            return []
        found = []
        for path in self.root.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                found.append(
                    DevMessage(
                        id=str(data["id"]),
                        to=str(data["to"]),
                        subject=str(data["subject"]),
                        template=str(data["template"]),
                        links=tuple(str(link) for link in data.get("links", [])),
                        text=str(data.get("text", "")),
                        sent_at=datetime.fromisoformat(str(data["sent_at"])),
                    )
                )
            except OSError, ValueError, KeyError:
                continue  # WHY: a stray or broken file in a dev folder must not break the route
        return sorted(found, key=lambda m: (m.sent_at, m.id))

    def latest(self, to: str, template: str | None = None) -> DevMessage | None:
        """The newest message to `to` (any letter case), optionally of one template."""
        wanted = to.strip().lower()
        matching = [
            m
            for m in self.messages()
            if m.to.lower() == wanted and (template is None or m.template == template)
        ]
        return matching[-1] if matching else None
