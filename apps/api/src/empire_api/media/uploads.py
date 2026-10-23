"""Getting files into the library: photos through the API, videos and documents straight from
the browser to the store with a signature, then confirmed here.

Collaborators: sniff.py (photo check), store.py, links.py (attach in the same transaction),
events.py, rules.py; routes.py (HTTP and the capped body reader).
Implements: ARCHITECTURE §12, SECURITY.md §6 (magic bytes, 10 MB photos, 100 MB video, 10 MB
documents, generated public ids, signature scoped to one public id, reply verified and the
asset re-read from the store before anything is saved), D-033.

SECURITY: the uploaded filename is never stored or sent to the store; public ids are
`empire/<APP_ENV>/<kind>/<uuid7>` (plus the extension for Office files, which the store needs).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Final

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from empire_api.errors import ApiProblem
from empire_api.ids import new_id
from empire_api.logs import get_logger
from empire_api.media import events, scrub, sniff
from empire_api.media.links import LINK_CONFLICTS, attach
from empire_api.media.models import Media, UploadIntent
from empire_api.media.rules import Owner, check_label, check_role, normalise_month
from empire_api.media.schemas import ImageUploadFields, UploadConfirm, UploadSignatureRequest
from empire_api.media.store import (
    InvalidReplyError,
    MediaStore,
    ReplyRef,
    SignedUpload,
    StoredAsset,
    StoreError,
    folder_for,
    get_store,
)
from empire_api.media.vocab import (
    CLOCK_SKEW_SECONDS,
    DIRECT_MAX_BYTES,
    DIRECT_TYPES,
    INTENT_TTL_SECONDS,
    MAX_IMAGE_PIXELS,
    VIDEO_TYPES,
)
from empire_api.projects.common import Actor, commit, record, snapshot
from empire_api.projects.media_owners import lock_owner_project, owner_project_id
from empire_api.timeutil import IST, utcnow

STORE_DOWN: Final = "The media service didn't respond. Please try again in a minute."
NOT_YOURS: Final = "This upload doesn't match one you started here. Upload the file again."
ALREADY_SAVED: Final = "This upload has already been saved to the library."
EXPIRED: Final = "The upload took longer than an hour to confirm. Upload the file again."
BAD_REPLY: Final = "The upload reply couldn't be verified. Upload the file again."
# An intent expires when its signature dies at the store (INTENT_TTL_SECONDS); allow for
# clock skew before the clean-up treats an unconfirmed upload as final and destroys it.
CLOCK_SKEW: Final = timedelta(seconds=CLOCK_SKEW_SECONDS)
KEEP_USED_INTENTS: Final = timedelta(days=7)
_DEFAULT_TITLES: Final = {"image": "Photo", "video": "Video", "document": "Document"}

log = get_logger(__name__)


def _default_title(kind: str) -> str:
    return f"{_DEFAULT_TITLES[kind]} {datetime.now(IST):%d %b %Y}"


def _unsupported(message: str) -> ApiProblem:
    return ApiProblem(415, message, errors=[{"field": "file", "message": message}])


def _invalid(field: str, message: str) -> ApiProblem:
    return ApiProblem(422, message, errors=[{"field": field, "message": message}])


@dataclass(frozen=True)
class NewMedia:
    """What gets saved for a new library item, besides what the store reported."""

    kind: str
    title: str | None
    alt_text: str | None = None
    label: str | None = None
    label_month: date | None = None
    attach_to: str | None = None
    role: str | None = None
    is_sample: bool = False


def _precheck_owner(db: Session, new: NewMedia, file_format: str | None) -> Owner | None:
    """Fail before uploading anything when the owner or role can't take this file."""
    if new.attach_to is None or new.role is None:
        return None
    owner = Owner.parse(new.attach_to)
    if owner_project_id(db, owner.type, owner.id) is None:
        raise ApiProblem(404, f"No {owner.type.replace('_', ' ')} with this id.")
    check_role(owner, new.role, Media(kind=new.kind, format=file_format or ""))
    return owner


def save_new_media(
    db: Session, actor: Actor, store: MediaStore, asset: StoredAsset, new: NewMedia
) -> Media:
    """Save the row, optionally attach it, audit, emit `media.added`, and commit (one unit)."""
    owner = Owner.parse(new.attach_to) if new.attach_to else None
    project = lock_owner_project(db, owner.type, owner.id) if owner else None
    media = Media(
        kind=new.kind,
        store=store.name,
        public_id=asset.public_id,
        resource_type=asset.resource_type,
        version=asset.version,
        format=asset.format,
        bytes=asset.bytes,
        width=asset.width,
        height=asset.height,
        duration_s=asset.duration_s,
        title=new.title or _default_title(new.kind),
        alt_text=new.alt_text,
        label=new.label,
        label_month=new.label_month,
        is_sample=new.is_sample,
        created_by=actor.user_id,
    )
    db.add(media)
    db.flush()
    record(
        db,
        actor,
        action="media.uploaded",
        entity_type="media",
        entity_id=media.id,
        before={},
        after=snapshot(media, ("created_by",)),
    )
    link = None
    if owner is not None and project is not None and new.role is not None:
        link = attach(
            db, actor, media=media, owner=owner, role=new.role, is_visible=True, project=project
        )
    events.media_event(db, actor, "media.added", media, "uploaded", link=link, project=project)
    if link is not None and owner is not None and project is not None:
        events.owner_changed(db, actor, project, owner, link.role, "attached")
    commit(db, LINK_CONFLICTS)
    return media


# --- Photos through the API ------------------------------------------------------------------


def checked_photo(data: bytes) -> scrub.CleanImage:
    """What the photo is (415 / 422) and the same photo without embedded metadata.

    SECURITY: every photo loses its EXIF (GPS), XMP, IPTC and comments here, before any store
    sees it (scrub.py explains why delivery-time stripping isn't enough).
    """
    try:
        return scrub.strip_metadata(data, sniff.inspect_image(data))
    except sniff.NotAnImageError as exc:
        raise _unsupported(str(exc)) from exc
    except sniff.TooManyPixelsError as exc:
        megapixels = MAX_IMAGE_PIXELS // 1_000_000
        raise _invalid(
            "file",
            f"This photo is larger than {megapixels} megapixels. Resize it (long edge "
            "2,560 px is plenty) and upload it again.",
        ) from exc
    except (OSError, ValueError) as exc:  # Pillow failed to decode or re-encode it
        raise _unsupported("This image file is damaged or isn't what it claims to be.") from exc


def upload_image(db: Session, actor: Actor, data: bytes, fields: ImageUploadFields) -> Media:
    """Check, clean, upload and save one photo (POST /admin/media/images).

    How it works:
      1. Magic bytes and Pillow decide what the file is (415) and its size (422 above 25 MP);
         embedded metadata is removed and the EXIF orientation applied (scrub.py).
      2. The owner and role are checked before anything is uploaded.
      3. Upload the cleaned bytes to the store under a generated public id.
      4. Save the row (and the link) in one transaction. If that fails, the uploaded file is
         destroyed again (best effort, logged) so the store holds no orphan.
    """
    clean = checked_photo(data)  # 1
    info = clean.info
    check_label("image", fields.label)
    new = NewMedia(
        kind="image",
        title=fields.title,
        alt_text=fields.alt_text,
        label=fields.label,
        label_month=normalise_month(fields.label_month),
        attach_to=fields.attach_to,
        role=fields.role,
    )
    _precheck_owner(db, new, info.format)  # 2
    db.rollback()  # WHY: release the read transaction before the slow upload
    store = get_store()
    try:
        asset = store.upload_image(  # 3
            clean.data,
            folder=folder_for("image"),
            public_id=str(new_id()),
            image_format=info.format,
        )
    except StoreError as exc:
        raise ApiProblem(503, STORE_DOWN) from exc
    if asset.width is None:
        asset = replace(asset, width=info.width, height=info.height)
    try:
        return save_new_media(db, actor, store, asset, new)  # 4
    except Exception:
        db.rollback()
        destroy_quietly(store, asset.resource_type, asset.public_id)
        raise


def destroy_quietly(store: MediaStore, resource_type: str, public_id: str) -> None:
    """Best-effort clean-up after a failed save. Never raises; logs ids only."""
    try:
        store.destroy(resource_type, public_id)
    except Exception:
        log.exception("media_orphan_destroy_failed", store=store.name, public_id=public_id)


# --- Direct uploads: signature ---------------------------------------------------------------


def _extension(filename: str) -> str:
    name = filename.strip().rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return name.rpartition(".")[2].lower() if "." in name else ""


def create_signature(
    db: Session, actor: Actor, body: UploadSignatureRequest
) -> tuple[UploadIntent, SignedUpload, str, str]:
    """Check the declared file, record an intent and sign the upload.

    Returns the intent, the signed upload, the folder and the signed (short) public id.
    """
    types = DIRECT_TYPES[body.kind]
    extension = _extension(body.filename)
    if extension not in types:
        allowed = ", ".join(e.upper() for e in types)
        raise _unsupported(f"Only {allowed} files can be uploaded here.")
    mime_types, resource_type = types[extension]
    if body.mime_type.strip().lower() not in mime_types:
        raise _unsupported(f"This file's type doesn't match a .{extension} file.")
    max_bytes = DIRECT_MAX_BYTES[body.kind]
    if body.bytes > max_bytes:
        limit = max_bytes // (1024 * 1024)
        raise ApiProblem(413, f"This file is larger than {limit} MB, the most the plan allows.")
    folder = folder_for(body.kind)
    short_id = str(new_id()) + (f".{extension}" if resource_type == "raw" else "")
    allowed_formats = tuple(VIDEO_TYPES) if body.kind == "video" else (extension,)
    signed = get_store().sign_upload(
        resource_type=resource_type,
        folder=folder,
        public_id=short_id,
        allowed_formats=allowed_formats,
    )
    intent = UploadIntent(
        public_id=f"{folder}/{short_id}",
        kind=body.kind,
        resource_type=resource_type,
        max_bytes=max_bytes,
        created_by=actor.user_id,
        expires_at=utcnow() + timedelta(seconds=INTENT_TTL_SECONDS),
    )
    db.add(intent)
    db.commit()
    return intent, signed, folder, short_id


# --- Direct uploads: confirm -----------------------------------------------------------------


def _expected_format(intent: UploadIntent) -> str | None:
    """The format the intent allows: pdf for image documents, the extension for raw files."""
    if intent.resource_type == "raw":
        return intent.public_id.rpartition(".")[2]
    if intent.kind == "document":
        return "pdf"
    return None


def _asset_problem(intent: UploadIntent, asset: StoredAsset | None, ref: ReplyRef) -> str | None:
    """Why the stored file can't be saved, or None. Checks the store's own record only."""
    if asset is None:
        return "The file didn't reach the media store. Upload it again."
    expected = _expected_format(intent)
    wrong_type = asset.resource_type != intent.resource_type or (
        asset.format != expected if expected else asset.format not in VIDEO_TYPES
    )
    if wrong_type or asset.version != ref.version:
        return "The stored file isn't the type that was signed for. Upload it again."
    if asset.bytes > intent.max_bytes:
        limit = intent.max_bytes // (1024 * 1024)
        return f"The stored file is larger than {limit} MB. It has been removed."
    return None


def _locked_intent(db: Session, actor: Actor, ref: ReplyRef) -> UploadIntent:
    intent = db.scalar(
        select(UploadIntent).where(UploadIntent.public_id == ref.public_id).with_for_update()
    )
    # SECURITY: another user's intent looks exactly like no intent (no hint that it exists).
    if intent is None or intent.created_by != actor.user_id:
        raise _invalid("cloudinary_response", NOT_YOURS)
    if intent.used_at is not None:
        raise _invalid("cloudinary_response", ALREADY_SAVED)
    return intent


def confirm_upload(db: Session, actor: Actor, body: UploadConfirm) -> Media:
    """Save a direct upload (POST /admin/media/confirm).

    How it works:
      1. Verify the reply's signature (public id + version) with the store's secret.
      2. Lock the matching intent: same user, unused, not expired. Mark it used, so a reply can
         be confirmed only once.
      3. Check the owner and role, if attaching, before going further.
      4. Re-read the asset from the store and check its type, format, version and size.
         Anything wrong → the file is destroyed (outbox) and the answer is 422.
      5. Save the row (and link) with the intent's `used_at` in one commit.
    """
    store = get_store()
    try:
        ref = store.verify_reply(body.cloudinary_response)  # 1
    except InvalidReplyError as exc:
        raise _invalid("cloudinary_response", BAD_REPLY) from exc
    intent = _locked_intent(db, actor, ref)  # 2
    now = utcnow()
    intent.used_at = now
    if intent.expires_at < now:
        events.upload_discarded(db, intent, store.name, "expired", actor.user_id)
        db.commit()
        raise _invalid("cloudinary_response", EXPIRED)
    new = NewMedia(kind=intent.kind, title=body.title, attach_to=body.attach_to, role=body.role)
    _precheck_owner(db, new, _expected_format(intent))  # 3
    try:
        asset = store.lookup(intent.resource_type, intent.public_id)  # type: ignore[arg-type]
    except StoreError as exc:
        raise ApiProblem(503, STORE_DOWN) from exc
    problem = _asset_problem(intent, asset, ref)  # 4
    if problem or asset is None:
        events.upload_discarded(db, intent, store.name, "refused", actor.user_id)
        db.commit()
        raise _invalid("cloudinary_response", problem or BAD_REPLY)
    return save_new_media(db, actor, store, asset, new)  # 5


def discard_stale_intents(db: Session, now: datetime) -> int:
    """Daily clean-up: destroy uploads that were signed but never confirmed, drop old intents.

    Caller commits. Returns how many unconfirmed uploads were sent to be destroyed.
    """
    store_name = get_store().name
    stale = db.scalars(
        select(UploadIntent).where(
            UploadIntent.used_at.is_(None),
            UploadIntent.expires_at < now - CLOCK_SKEW,
        )
    ).all()
    for intent in stale:
        events.upload_discarded(db, intent, store_name, "never_confirmed", None)
        db.delete(intent)
    db.execute(delete(UploadIntent).where(UploadIntent.used_at < now - KEEP_USED_INTENTS))
    return len(stale)
