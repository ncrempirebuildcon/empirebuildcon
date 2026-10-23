"""Sample media for `empire-api seed --sample`: a few generated placeholder tiles in each sample
project's photo list, through the fake store only.

Collaborators: cli.py (after projects.seed.seed_sample), store.py, projects/media_owners.py.
Implements: D-015 (sample data), CODE_STYLE §7 (honest seeds).

COMPLIANCE (AGENTS.md "Honest content"): the tiles are plain dark rectangles that say "SAMPLE"
and "Placeholder N - not a real photo". They are never photographs, never labelled as actual or
progress photos, carry `is_sample = true`, and are only made with the fake store (never
uploaded to Cloudinary). No RERA QR is seeded: a sample project still shows "RERA QR code
missing" until staff upload a real one.
Idempotent: a project that already has photos is skipped.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Final

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from empire_api.ids import new_id
from empire_api.media.models import Media, MediaLink
from empire_api.media.store import folder_for, get_store
from empire_api.projects.media_owners import sample_project_ids

TILES_PER_PROJECT: Final = 3
HEADLINE: Final = "SAMPLE"
# WHY a plain hyphen: Pillow's built-in font has no em dash (it drew a missing-glyph box).
CAPTION: Final = "Placeholder {number} - not a real photo"
TILE_SIZE: Final = (1280, 853)
# Empire Black & gold tokens (brand/tokens/empire-noir.json): noir-800, gold-500, muted.
INK: Final = (0x17, 0x14, 0x11)
GOLD: Final = (0xD9, 0xA4, 0x41)
MUTED: Final = (0xA8, 0x9A, 0x86)


@dataclass(frozen=True)
class SampleMediaResult:
    added: int
    skipped_projects: int
    store: str


def sample_tile(number: int) -> bytes:
    """A PNG placeholder: "SAMPLE" and "Placeholder N - not a real photo" on a plain tile.

    Tile text uses ASCII only, which Pillow's built-in font can draw.
    """
    image = Image.new("RGB", TILE_SIZE, INK)
    draw = ImageDraw.Draw(image)
    width, height = TILE_SIZE
    draw.rectangle((24, 24, width - 25, height - 25), outline=GOLD, width=4)
    draw.text(
        (width // 2, height // 2 - 40),
        HEADLINE,
        fill=GOLD,
        font=ImageFont.load_default(size=140),
        anchor="mm",
    )
    draw.text(
        (width // 2, height // 2 + 90),
        CAPTION.format(number=number),
        fill=MUTED,
        font=ImageFont.load_default(size=40),
        anchor="mm",
    )
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def seed_sample_media(db: Session) -> SampleMediaResult:
    """Add placeholder photos to the sample projects. Caller commits.

    Does nothing (added = 0) when the active store isn't the fake one.
    """
    store = get_store()
    if store.name != "fake":
        return SampleMediaResult(added=0, skipped_projects=0, store=store.name)
    added = skipped = 0
    for project_id in sample_project_ids(db):
        has_photos = db.scalar(
            select(exists().where(MediaLink.project_id == project_id, MediaLink.role == "gallery"))
        )
        if has_photos:
            skipped += 1
            continue
        for number in range(1, TILES_PER_PROJECT + 1):
            asset = store.upload_image(
                sample_tile(number),
                folder=folder_for("image"),
                public_id=str(new_id()),
                image_format="png",
            )
            media = Media(
                kind="image",
                store=store.name,
                public_id=asset.public_id,
                resource_type="image",
                version=asset.version,
                format="png",
                bytes=asset.bytes,
                width=asset.width,
                height=asset.height,
                title=f"SAMPLE — placeholder {number}",
                alt_text="Sample placeholder tile, not a real photo",
                is_sample=True,
            )
            db.add(media)
            db.flush()
            db.add(
                MediaLink(
                    media_id=media.id, project_id=project_id, role="gallery", sort_order=number - 1
                )
            )
            added += 1
    db.flush()
    return SampleMediaResult(added=added, skipped_projects=skipped, store=store.name)
