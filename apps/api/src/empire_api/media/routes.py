"""Media endpoints: /api/v1/admin/media/** and /api/v1/admin/media-links/** (design contract
tag "Media").

HTTP only: the rules are in uploads.py, library.py and links.py. Permissions (ARCHITECTURE §11):
everything needs `media.upload` except deleting from the library, which needs `media.manage`.

SECURITY: uploads and upload signatures count against one per-user limit (120 per 10 minutes).
The photo endpoint reads its own body with a hard 10 MB cap (multipart.py), so it is `async`
and runs the database work in the thread pool like every other (sync) route.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Final

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from pydantic_core import PydanticCustomError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from empire_api.db import get_db
from empire_api.errors import ApiProblem, problem_responses
from empire_api.integrations.outbox_drain import drain_soon
from empire_api.media import library, links, present, uploads
from empire_api.media.models import Media as MediaRow
from empire_api.media.models import MediaLink
from empire_api.media.multipart import read_capped_form
from empire_api.media.rules import Owner
from empire_api.media.schemas import (
    ImageUploadFields,
    LinkedMedia,
    Media,
    MediaLinkInput,
    MediaLinkUpdate,
    MediaList,
    MediaUpdate,
    UploadConfirm,
    UploadSignature,
    UploadSignatureRequest,
    check_attach_to,
)
from empire_api.media.vocab import MAX_IMAGE_BYTES, UPLOAD_LIMIT, UPLOAD_WINDOW_SECONDS, MediaKind
from empire_api.pagination import PageParams, page_params
from empire_api.platform import rate_limit
from empire_api.platform.crypto import client_ip
from empire_api.projects.common import Actor
from empire_api.projects.schemas_shared import ReorderRequest
from empire_api.users.deps import require, staff
from empire_api.users.schemas import PageMeta
from empire_api.users.sessions import SessionInfo

router = APIRouter(
    prefix="/api/v1/admin", tags=["Media"], responses=problem_responses(401, 403, 404, 422)
)
Db = Annotated[Session, Depends(get_db)]
Paging = Annotated[PageParams, Depends(page_params)]
Uploader = Annotated[SessionInfo, Depends(require("media.upload"))]
Manager = Annotated[SessionInfo, Depends(require("media.manage"))]
MediaId = Annotated[uuid.UUID, Path(alias="id")]
LinkId = Annotated[uuid.UUID, Path(alias="id")]
TOO_LARGE_PHOTO: Final = "This photo is larger than 10 MB. Resize it and upload it again."
TOO_MANY: Final = "Too many uploads in a short time. Wait a few minutes and try again."
IMAGE_BODY: Final = {
    "required": True,
    "content": {"multipart/form-data": {"schema": {"$ref": "#/components/schemas/ImageUpload"}}},
}


def actor_of(info: SessionInfo, request: Request) -> Actor:
    return Actor(user_id=info.user.id, ip=client_ip(request))


def _limit_uploads(info: SessionInfo) -> None:
    """SECURITY: one counter per staff member for photos and signatures together."""
    rate_limit.enforce(
        f"media:upload:user:{info.user.id}",
        limit=UPLOAD_LIMIT,
        window_seconds=UPLOAD_WINDOW_SECONDS,
        message=TOO_MANY,
    )


def _media(db: Session, row_id: uuid.UUID) -> Media:
    """The library item as the API returns it, read fresh after a change."""
    db.expire_all()
    row = db.get(MediaRow, row_id)
    if row is None:
        raise ApiProblem(404, library.NO_MEDIA)
    return present.media_list(db, [row])[0]


def _linked(db: Session, link: MediaLink) -> LinkedMedia:
    db.refresh(link)
    counts = present.attached_counts(db, [link.media_id])
    return present.linked_out(link, counts.get(link.media_id, 0))


def _owner_filter(value: str | None) -> Owner | None:
    if value is None:
        return None
    try:
        return Owner.parse(check_attach_to(value))
    except PydanticCustomError as exc:
        message = str(exc)
        raise ApiProblem(
            422, message, errors=[{"field": "attached_to", "message": message}]
        ) from exc


# --- Library ---------------------------------------------------------------------------------


@router.get(
    "/media",
    response_model=MediaList,
    operation_id="list_media",
    summary="Media library",
    **staff("media.upload"),
)
def list_media(
    actor: Uploader,
    db: Db,
    paging: Paging,
    q: Annotated[
        str | None, Query(max_length=100, description="Title or alt text contains")
    ] = None,
    kind: MediaKind | None = None,
    attached_to: Annotated[
        str | None, Query(max_length=80, description="owner_type:owner_id, e.g. project:<uuid>")
    ] = None,
    unattached: Annotated[bool, Query(description="Only files nothing uses")] = False,
) -> MediaList:
    """Newest first. `unattached=true` lists files nothing uses (safe to delete)."""
    filters = library.MediaFilters(kind, q, _owner_filter(attached_to), unattached)
    rows, total = library.list_media(db, paging, filters)
    return MediaList(items=present.media_list(db, rows), meta=PageMeta(**paging.meta(total)))


@router.patch(
    "/media/{id}",
    response_model=Media,
    operation_id="update_media",
    summary="Rename / alt text",
    **staff("media.upload", write=True),
)
def update_media(
    media_id: MediaId, body: MediaUpdate, actor: Uploader, request: Request, db: Db
) -> Media:
    """Title, alt text and the honest label (label_month: any day of the month)."""
    row = library.update_media(db, actor_of(actor, request), media_id, body)
    return _media(db, row.id)


@router.delete(
    "/media/{id}",
    status_code=204,
    operation_id="delete_media",
    summary="Delete from library and Cloudinary (refused while attached)",
    responses=problem_responses(409),
    **staff("media.manage", write=True),
)
def delete_media(
    media_id: MediaId, actor: Manager, request: Request, db: Db, background: BackgroundTasks
) -> Response:
    library.delete_media(db, actor_of(actor, request), media_id)
    drain_soon(background)  # destroy the stored file within seconds; the sweep retries
    return Response(status_code=204)


# --- Uploads ---------------------------------------------------------------------------------


def _with_request_body(kwargs: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """`staff()` route kwargs plus a hand-written request body for the spec."""
    return {**kwargs, "openapi_extra": {**kwargs["openapi_extra"], "requestBody": body}}


def _image_fields(raw: dict[str, str]) -> ImageUploadFields:
    try:
        return ImageUploadFields.model_validate(raw)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


@router.post(
    "/media/images",
    status_code=201,
    response_model=Media,
    operation_id="upload_image",
    summary="Upload a photo through the API (magic-byte check, 10 MB limit)",
    responses={
        **problem_responses(413, 429, 503),
        415: {"description": "Not a JPEG, PNG, WebP or AVIF image"},
    },
    **_with_request_body(staff("media.upload", write=True), IMAGE_BODY),
)
async def upload_image(request: Request, actor: Uploader, db: Db) -> Media:
    """Multipart `ImageUpload`. Optional `attach_to` + `role` attach it in the same step."""
    await run_in_threadpool(_limit_uploads, actor)
    form = await read_capped_form(request, MAX_IMAGE_BYTES, TOO_LARGE_PHOTO)
    try:
        if form.file is None:
            raise ApiProblem(
                422, "Choose a photo to upload.", errors=[{"field": "file", "message": "Required"}]
            )
        data = await form.file.read()
        fields = _image_fields(form.fields)
    finally:
        await form.close()
    row = await run_in_threadpool(uploads.upload_image, db, actor_of(actor, request), data, fields)
    return await run_in_threadpool(_media, db, row.id)


@router.post(
    "/media/upload-signature",
    response_model=UploadSignature,
    operation_id="media_upload_signature",
    summary="Signed parameters for a direct video/document upload to Cloudinary",
    description=(
        "Video ≤ 100 MB; documents (PDF, DOC/DOCX, PPT/PPTX) ≤ 10 MB on the Cloudinary free "
        "plan. POST the file to `upload_url` as multipart with every entry of `fields`, then "
        "send the store's JSON reply, unchanged, to `confirm` within an hour (expires_at)."
    ),
    responses={
        **problem_responses(429),
        413: {"description": "File too large for the plan"},
        415: {"description": "File type not allowed"},
    },
    **staff("media.upload", write=True),
)
def media_upload_signature(
    body: UploadSignatureRequest, actor: Uploader, request: Request, db: Db
) -> UploadSignature:
    _limit_uploads(actor)
    intent, signed, folder, short_id = uploads.create_signature(db, actor_of(actor, request), body)
    return UploadSignature(
        upload_url=signed.upload_url,
        api_key=signed.api_key,
        timestamp=signed.timestamp,
        signature=signed.signature,
        folder=folder,
        public_id=short_id,
        resource_type=intent.resource_type,
        max_bytes=intent.max_bytes,
        fields=signed.fields,
        expires_at=intent.expires_at,
    )


@router.post(
    "/media/confirm",
    status_code=201,
    response_model=Media,
    operation_id="media_confirm_upload",
    summary="Save a direct upload after verifying Cloudinary's signed reply",
    responses={**problem_responses(400, 503)},
    **staff("media.upload", write=True),
)
def media_confirm_upload(body: UploadConfirm, actor: Uploader, request: Request, db: Db) -> Media:
    """422 when the reply doesn't verify or match an upload you started in the last hour,
    or when the stored file isn't what was signed for. A refused file is destroyed by the
    outbox (the next sweep, at most 15 minutes later)."""
    row = uploads.confirm_upload(db, actor_of(actor, request), body)
    return _media(db, row.id)


# --- Links -----------------------------------------------------------------------------------


@router.post(
    "/media-links",
    status_code=201,
    response_model=LinkedMedia,
    operation_id="attach_media",
    summary="Attach media to a project, configuration, update, page or post",
    responses=problem_responses(409),
    **staff("media.upload", write=True),
)
def attach_media(body: MediaLinkInput, actor: Uploader, request: Request, db: Db) -> LinkedMedia:
    """Single-valued roles (brochure, rera_qr, hero, og_image, floor_plan) replace the current
    link; the old file stays in the library. Pages and posts arrive in part 4."""
    link = links.attach_media(
        db, actor_of(actor, request), body.media_id, body.attach_to, body.role, body.is_visible
    )
    return _linked(db, link)


@router.patch(
    "/media-links/{id}",
    response_model=LinkedMedia,
    operation_id="update_media_link",
    summary="Show/hide on website, make cover",
    responses=problem_responses(409),
    **staff("media.upload", write=True),
)
def update_media_link(
    link_id: LinkId, body: MediaLinkUpdate, actor: Uploader, request: Request, db: Db
) -> LinkedMedia:
    """Hidden items can't be the cover; hiding the cover unpins it. A live project's RERA QR
    can't be hidden (409)."""
    link = links.update_link(db, actor_of(actor, request), link_id, body)
    return _linked(db, link)


@router.delete(
    "/media-links/{id}",
    status_code=204,
    operation_id="detach_media",
    summary="Detach (media stays in the library)",
    responses=problem_responses(409),
    **staff("media.upload", write=True),
)
def detach_media(link_id: LinkId, actor: Uploader, request: Request, db: Db) -> Response:
    links.detach(db, actor_of(actor, request), link_id)
    return Response(status_code=204)


@router.put(
    "/media-links/order",
    status_code=204,
    operation_id="reorder_media_links",
    summary="Set order for one owner+role (first = cover unless pinned)",
    **staff("media.upload", write=True),
)
def reorder_media_links(
    body: ReorderRequest, actor: Uploader, request: Request, db: Db
) -> Response:
    """`ids`: every link of one owner and role, each once, in the new order."""
    links.reorder(db, actor_of(actor, request), body.ids)
    return Response(status_code=204)


def openapi_components() -> dict[str, Any]:
    """Schemas this module adds to the spec by hand (main.py)."""
    from empire_api.media.schemas import IMAGE_UPLOAD_SCHEMA  # noqa: PLC0415

    return {"ImageUpload": IMAGE_UPLOAD_SCHEMA}
