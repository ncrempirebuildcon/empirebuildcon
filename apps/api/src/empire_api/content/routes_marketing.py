"""FAQ, testimonial and offer endpoints: /api/v1/admin/faqs/** and /testimonials/** (design
contract tag "Content") and /api/v1/admin/offers/** (tag "Marketing").

HTTP only: the rules are in faqs.py, testimonials.py and offers.py. Permissions (ARCHITECTURE
§11, design contract): FAQs read `content.read`, write `content.write` (showing one needs
`content.publish`, checked in faqs.py); testimonials read `content.read`, write
`content.publish`; offers `offers.manage`.
TODO(phase-5): the public `/api/v1/public/faqs` and `/api/v1/public/testimonials`.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from sqlalchemy.orm import Session

from empire_api.content import faqs, offers, present, testimonials
from empire_api.content.common import editor_of
from empire_api.content.schemas_marketing import (
    Faq,
    FaqInput,
    FaqList,
    FaqUpdate,
    Offer,
    OfferInput,
    OfferList,
    OfferUpdate,
    Testimonial,
    TestimonialInput,
    TestimonialList,
    TestimonialUpdate,
)
from empire_api.content.vocab import OfferPlacement, OfferState
from empire_api.db import get_db
from empire_api.errors import problem_responses
from empire_api.pagination import PageParams, page_params
from empire_api.projects.schemas_shared import ReorderRequest
from empire_api.timeutil import utcnow
from empire_api.users.deps import require, staff
from empire_api.users.schemas import PageMeta
from empire_api.users.sessions import SessionInfo

_ERRORS = problem_responses(401, 403, 404, 422)
router = APIRouter(prefix="/api/v1/admin", tags=["Content"], responses=_ERRORS)
offers_router = APIRouter(prefix="/api/v1/admin", tags=["Marketing"], responses=_ERRORS)
Db = Annotated[Session, Depends(get_db)]
Paging = Annotated[PageParams, Depends(page_params)]
Reader = Annotated[SessionInfo, Depends(require("content.read"))]
Writer = Annotated[SessionInfo, Depends(require("content.write"))]
Publisher = Annotated[SessionInfo, Depends(require("content.publish"))]
OfferManager = Annotated[SessionInfo, Depends(require("offers.manage"))]
ItemId = Annotated[uuid.UUID, Path(alias="id")]
CONFLICT = problem_responses(409)


# --- FAQs ------------------------------------------------------------------------------------


@router.get(
    "/faqs",
    response_model=FaqList,
    operation_id="list_faqs",
    summary="List faqs",
    **staff("content.read"),
)
def list_faqs(
    actor: Reader,
    db: Db,
    paging: Paging,
    project_id: uuid.UUID | None = None,
    site_wide: Annotated[
        bool, Query(description="Only the site-wide FAQs (no project); an addition")
    ] = False,
) -> FaqList:
    """Site-wide first, then by project, each list in its order."""
    rows, total = faqs.list_faqs(db, paging, project_id, site_wide)
    return FaqList(items=present.faqs_out(db, rows), meta=PageMeta(**paging.meta(total)))


@router.post(
    "/faqs",
    status_code=201,
    response_model=Faq,
    operation_id="create_faq",
    summary="Create faq",
    **staff("content.write", write=True),
)
def create_faq(body: FaqInput, actor: Writer, request: Request, db: Db) -> Faq:
    """Added at the end of its list. Showing it (`is_visible`, default true) needs
    `content.publish`."""
    row = faqs.create_faq(db, editor_of(actor, request), body)
    return present.faqs_out(db, [row])[0]


@router.put(
    "/faqs/order",
    response_model=list[Faq],
    operation_id="reorder_faqs",
    summary="Set the order of one FAQ list (site-wide, or one project's)",
    **staff("content.write", write=True),
)
def reorder_faqs(body: ReorderRequest, actor: Writer, request: Request, db: Db) -> list[Faq]:
    """An addition (Phase 4 part 4): send every FAQ of the list once, in the new order."""
    rows = faqs.reorder_faqs(db, editor_of(actor, request), body.ids)
    return present.faqs_out(db, rows)


@router.patch(
    "/faqs/{id}",
    response_model=Faq,
    operation_id="update_faq",
    summary="Update faq",
    **staff("content.write", write=True),
)
def update_faq(faq_id: ItemId, body: FaqUpdate, actor: Writer, request: Request, db: Db) -> Faq:
    row = faqs.update_faq(db, editor_of(actor, request), faq_id, body)
    return present.faqs_out(db, [row])[0]


@router.delete(
    "/faqs/{id}",
    status_code=204,
    operation_id="delete_faq",
    summary="Delete faq",
    **staff("content.write", write=True),
)
def delete_faq(faq_id: ItemId, actor: Writer, request: Request, db: Db) -> Response:
    """Also removes it from every page block that picked it."""
    faqs.delete_faq(db, editor_of(actor, request), faq_id)
    return Response(status_code=204)


# --- Testimonials ----------------------------------------------------------------------------


@router.get(
    "/testimonials",
    response_model=TestimonialList,
    operation_id="list_testimonials",
    summary="List testimonials",
    **staff("content.read"),
)
def list_testimonials(
    actor: Reader,
    db: Db,
    paging: Paging,
    project_id: uuid.UUID | None = None,
    is_visible: bool | None = None,
) -> TestimonialList:
    """Newest first. `project_id` and `is_visible` are additions."""
    rows, total = testimonials.list_testimonials(db, paging, project_id, is_visible)
    return TestimonialList(
        items=present.testimonials_out(db, rows), meta=PageMeta(**paging.meta(total))
    )


@router.post(
    "/testimonials",
    status_code=201,
    response_model=Testimonial,
    operation_id="create_testimonial",
    summary="Create testimonial",
    **staff("content.publish", write=True),
)
def create_testimonial(
    body: TestimonialInput, actor: Publisher, request: Request, db: Db
) -> Testimonial:
    """Real testimonials only: showing one needs `source` and `consent_date`."""
    row = testimonials.create_testimonial(db, editor_of(actor, request), body)
    return present.testimonials_out(db, [row])[0]


@router.patch(
    "/testimonials/{id}",
    response_model=Testimonial,
    operation_id="update_testimonial",
    summary="Update testimonial",
    **staff("content.publish", write=True),
)
def update_testimonial(
    testimonial_id: ItemId, body: TestimonialUpdate, actor: Publisher, request: Request, db: Db
) -> Testimonial:
    row = testimonials.update_testimonial(db, editor_of(actor, request), testimonial_id, body)
    return present.testimonials_out(db, [row])[0]


@router.delete(
    "/testimonials/{id}",
    status_code=204,
    operation_id="delete_testimonial",
    summary="Delete testimonial",
    **staff("content.publish", write=True),
)
def delete_testimonial(
    testimonial_id: ItemId, actor: Publisher, request: Request, db: Db
) -> Response:
    """Always allowed (consent can be withdrawn); it leaves every page block at once."""
    testimonials.delete_testimonial(db, editor_of(actor, request), testimonial_id)
    return Response(status_code=204)


# --- Offers ----------------------------------------------------------------------------------


@offers_router.get(
    "/offers",
    response_model=OfferList,
    operation_id="list_offers",
    summary="List offers",
    **staff("offers.manage"),
)
def list_offers(
    actor: OfferManager,
    db: Db,
    paging: Paging,
    active_on: Annotated[
        date | None, Query(description="Switched on and running on this IST day")
    ] = None,
    placement: OfferPlacement | None = None,
    state: OfferState | None = None,
    project_id: uuid.UUID | None = None,
) -> OfferList:
    """Highest priority first. `placement`, `state` and `project_id` are additions."""
    now = utcnow()
    filters = offers.OfferFilters(active_on, placement, state, project_id)
    rows, total = offers.list_offers(db, paging, filters, now)
    return OfferList(items=present.offers_out(db, rows, now), meta=PageMeta(**paging.meta(total)))


@offers_router.post(
    "/offers",
    status_code=201,
    response_model=Offer,
    operation_id="create_offer",
    summary="Create offer",
    **staff("offers.manage", write=True),
)
def create_offer(body: OfferInput, actor: OfferManager, request: Request, db: Db) -> Offer:
    """Saved switched off unless `is_active` is true. No countdowns, no pressure wording; a
    price or discount needs terms."""
    row = offers.create_offer(db, editor_of(actor, request), body)
    db.refresh(row)
    return present.offers_out(db, [row], utcnow())[0]


@offers_router.patch(
    "/offers/{id}",
    response_model=Offer,
    operation_id="update_offer",
    summary="Update offer",
    **staff("offers.manage", write=True),
)
def update_offer(
    offer_id: ItemId, body: OfferUpdate, actor: OfferManager, request: Request, db: Db
) -> Offer:
    row = offers.update_offer(db, editor_of(actor, request), offer_id, body)
    db.refresh(row)
    return present.offers_out(db, [row], utcnow())[0]


@offers_router.delete(
    "/offers/{id}",
    status_code=204,
    operation_id="delete_offer",
    summary="Delete offer",
    responses=CONFLICT,
    description="Only offers that were never on the website and no page block shows.",
    **staff("offers.manage", write=True),
)
def delete_offer(offer_id: ItemId, actor: OfferManager, request: Request, db: Db) -> Response:
    offers.delete_offer(db, editor_of(actor, request), offer_id)
    return Response(status_code=204)
