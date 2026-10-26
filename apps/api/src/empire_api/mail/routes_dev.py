"""Development-only dev mailbox (tag "Dev mail"): `GET /api/v1/dev-mail/latest?to=<email>`.

The browser suite reads a setup or reset link from here instead of a real inbox.

Collaborators: mail/dev.py (the stored messages); main.py mounts this router ONLY when the dev
transport is active AND APP_ENV is development or test (tests/test_mail_transport.py proves it
is absent otherwise, like the dev-media routes).

SECURITY: public on purpose (the suite has no session for an invited person), so it must never
exist where real people get real links: config.py refuses the dev transport in staging and
production, and main.py checks APP_ENV as well. Answers are `no-store`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field

from empire_api.errors import ApiProblem, problem_responses
from empire_api.mail.dev import DevTransport
from empire_api.mail.transport import get_transport
from empire_api.users.deps import PUBLIC

router = APIRouter(
    prefix="/api/v1/dev-mail", tags=["Dev mail"], responses=problem_responses(404, 422)
)


class DevMail(BaseModel):
    id: str
    to: str
    subject: str
    template: str = Field(description="e.g. setup_link, reset_link, lead_alert, account_locked")
    links: list[str] = Field(description="Every link in the message, in order")
    text: str = Field(description="The plain-text version")
    sent_at: datetime


@router.get(
    "/latest",
    response_model=DevMail,
    operation_id="dev_mail_latest",
    summary="The newest message to an address (dev transport only; development and test)",
    **PUBLIC,
)
def latest(
    response: Response,
    to: Annotated[str, Query(min_length=3, max_length=254)],
    template: Annotated[str | None, Query(max_length=40)] = None,
) -> DevMail:
    transport = get_transport()
    if not isinstance(transport, DevTransport):  # main.py mounts this only for the dev transport
        raise ApiProblem(404, "There is nothing at this address.")
    message = transport.latest(to, template)
    if message is None:
        raise ApiProblem(404, "No message to this address yet.")
    response.headers["Cache-Control"] = "no-store"
    return DevMail(
        id=message.id,
        to=message.to,
        subject=message.subject,
        template=message.template,
        links=list(message.links),
        text=message.text,
        sent_at=message.sent_at,
    )
