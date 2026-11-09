"""POST /api/v1/ai/chat: the website assistant (task 7.2, D-059; contract in phase-7/PLAN.md).

404 while the `chat_widget` flag is off. No session and no CSRF, like the public lead forms
(SECURITY.md §3): the route gives a session's cookie no authority and changes nothing but a
daily counter. A rate limit per address instead.

SECURITY/COMPLIANCE: the visitor's message is never stored or logged (only daily counts), and
phone numbers and emails are removed before it reaches the provider (ai/chat.py).
"""

from __future__ import annotations

from typing import Annotated, Final, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.orm import Session

from empire_api.ai import chat
from empire_api.ai.providers import get_provider
from empire_api.db import get_db
from empire_api.errors import PROBLEM_MEDIA_TYPE, ApiProblem, problem_responses
from empire_api.logs import get_logger
from empire_api.platform import rate_limit
from empire_api.platform.crypto import client_ip, hash_ip
from empire_api.site_settings.flags import is_enabled
from empire_api.users.deps import PUBLIC

log = get_logger(__name__)
LIMIT: Final = 12
WINDOW_SECONDS: Final = 600
RATE: Final = f"{LIMIT} messages per {WINDOW_SECONDS // 60} minutes per address"

router = APIRouter(prefix="/api/v1/ai", tags=["AI"], responses=problem_responses(404, 422, 429))
Db = Annotated[Session, Depends(get_db)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
TurnText = Annotated[str, StringConstraints(max_length=1000)]


class ChatTurnIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    text: TurnText


class ChatRequest(BaseModel):
    """The widget sends at most the last 2 turns (4 messages)."""

    model_config = ConfigDict(extra="forbid")
    message: Text
    history: list[ChatTurnIn] = Field(default_factory=list, max_length=4)
    # Long enough for an address with campaign parameters; only the path is used.
    page: Annotated[str, StringConstraints(max_length=2000)] | None = None


class ChatCitationOut(BaseModel):
    n: int
    url: str
    title: str


class ChatCardOut(BaseModel):
    slug: str


class ChatReply(BaseModel):
    """Either `answer` (with `citations` and `cards`) or, alone, `fallback`. `answer` is plain
    text; only its `[n]` markers mean something: a link to the citation whose `n` is that number
    (numbers keep the source order, so [1] and [3] can appear without [2])."""

    answer: str | None = None
    citations: list[ChatCitationOut] = Field(default_factory=list)
    cards: list[ChatCardOut] = Field(default_factory=list)
    fallback: Literal["no_answer", "busy"] | None = None


def _same_site_path(page: str | None) -> str | None:
    # Only used to prefer the current page's sources; anything else is ignored.
    if page and page.startswith("/") and not page.startswith("//"):
        return page.split("?", 1)[0].split("#", 1)[0]
    return None


@router.post(
    "/chat",
    response_model=ChatReply,
    response_model_exclude_none=True,
    operation_id="ai_chat",
    summary="Ask the website assistant (feature flag chat_widget; 404 when off)",
    description=(
        "Answers only from Empire's published content, with citations. Plain text; `[n]` "
        "markers link to `citations[n].url`. `fallback` is `no_answer` when nothing answers "
        "it and `busy` when the daily allocation is used or the model is slow or failing; "
        "the widget then offers WhatsApp, Call and Request a call back. 429 carries "
        "`retry_after_seconds`. Nothing typed is stored."
    ),
    openapi_extra={
        **PUBLIC["openapi_extra"],
        "x-rate-limit": RATE,
        "x-feature-flag": "chat_widget",
    },
)
def ai_chat(body: ChatRequest, request: Request, db: Db) -> ChatReply | JSONResponse:
    if not is_enabled(db, "chat_widget"):
        raise ApiProblem(404, "Not found.")
    # WHY per address, not per /24: mobile carriers put many visitors behind one network.
    address = hash_ip(client_ip(request))
    limited = rate_limit.hit(f"ai:ip:{address}", limit=LIMIT, window_seconds=WINDOW_SECONDS)
    if not limited.allowed:
        return JSONResponse(
            {
                "type": "about:blank",
                "title": "Too many requests",
                "status": 429,
                "detail": "You've asked a lot quickly. Please wait a minute.",
                "instance": request.url.path,
                "retry_after_seconds": limited.retry_after,
            },
            status_code=429,
            headers={"Retry-After": str(limited.retry_after)},
            media_type=PROBLEM_MEDIA_TYPE,
        )
    try:
        reply = chat.answer(
            db,
            get_provider(),
            message=body.message,
            history=[chat.Turn(t.role, t.text) for t in body.history],
            page=_same_site_path(body.page),
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001 — the visitor gets "busy", never an error page
        db.rollback()
        log.warning("ai.chat_failed", error=type(exc).__name__)  # the type only: no text
        return JSONResponse({"fallback": "busy"})
    if reply.fallback:
        return JSONResponse({"fallback": reply.fallback})  # exactly the contract's shape
    return ChatReply(
        answer=reply.answer,
        citations=[ChatCitationOut(n=c.n, url=c.url, title=c.title) for c in reply.citations],
        cards=[ChatCardOut(slug=s) for s in reply.cards],
    )
