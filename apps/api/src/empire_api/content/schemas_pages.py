"""Request and response shapes for pages and posts (design contract schemas Page, PageInput,
Post and PostInput; Block/BlockInput are in block_types.py).

Additions to the contract (D-035):
  - Page and Post: `path` (the address on the website), `seo_warnings` (CMS checklist),
    `publish_blockers`, `is_sample`, `published_at`, `created_at`/`created_by`, `updated_by`.
  - Page: `media` (the library items it uses, for thumbnails); Page and Post: `og_image` (the
    share image's library item, like ProjectAdmin.og_image).
  - PageInput: `legal_version` (legal pages only); `slug` may be left out (made from the title).
  - PATCH bodies are `PageUpdate` and `PostUpdate`: every field optional, and `publish_state`
    `archived` archives, `draft` restores (like ProjectUpdate, D-031).
  - Review fixes: Page and PageSummary `is_required` (L8); PageUpdate and PageBlocksInput
    `expected_updated_at` (L7: a save based on an older copy of the page answers 409).
  - The lists return `PageSummary` and `PostSummary` rows (no blocks or body).

SECURITY (SECURITY.md §5): unknown fields are refused, every string is bounded, and no text
accepts HTML (content/fields.py). Times must carry a time zone (stored in UTC).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Final, Literal

from pydantic import AfterValidator, AwareDatetime, Field, field_validator
from pydantic_core import PydanticCustomError

from empire_api.content.block_types import Block, BlockInput
from empire_api.content.fields import (
    Formatted50000,
    Plain20,
    Plain40,
    Plain120,
    Plain160,
    Plain300,
)
from empire_api.content.vocab import MAX_BLOCKS, MAX_TAGS, EditableKind, PageKind
from empire_api.media.schemas import Media
from empire_api.projects.fields import BlankIsNone, OutModel, Slug, StrictModel
from empire_api.projects.schemas_shared import Seo, Translations, check_translation_fields
from empire_api.projects.vocab import PublishState
from empire_api.seo.schemas import SeoWarning
from empire_api.users.schemas import PageMeta, UserRef

# Translatable fields and their English lengths; translations refuse HTML too (review L1).
PAGE_TRANSLATABLE: Final = {"title": 120}
POST_TRANSLATABLE: Final = {"title": 160, "excerpt": 300, "body": 50_000}
NavOrder = Annotated[int, Field(ge=0, le=10_000)]
EXPECTED: Final = (
    "The page's updated_at when the editor loaded it. If the page has been saved since, the "
    "save is refused (409) instead of overwriting that change. Leave it out to skip the check."
)
RestoreOrArchive = Literal["draft", "archived"]


def _page_translations(value: Translations) -> Translations:
    return check_translation_fields(value, PAGE_TRANSLATABLE, plain_text=True)


def _post_translations(value: Translations) -> Translations:
    return check_translation_fields(value, POST_TRANSLATABLE, plain_text=True)


def _not_null(value: Any) -> Any:
    if value is None:
        raise PydanticCustomError("not_null", "This can't be empty.")
    return value


PageTranslations = Annotated[Translations, AfterValidator(_page_translations)]
PostTranslations = Annotated[Translations, AfterValidator(_post_translations)]


# --- Pages -----------------------------------------------------------------------------------


class PageSummary(OutModel):
    """A row of the CMS pages list."""

    id: uuid.UUID
    slug: str
    path: str = Field(description="Address on the website: / for the home page, else /<slug>")
    title: str
    kind: PageKind
    publish_state: PublishState
    publish_at: datetime | None
    unpublish_at: datetime | None
    published_at: datetime | None = Field(description="First publish; never cleared")
    show_in_nav: bool
    nav_order: int | None
    legal_version: str | None
    is_draft_text: bool = Field(
        description="Legal page text is a Claude draft awaiting owner approval (D-017); "
        "production refuses to publish it"
    )
    is_sample: bool
    is_required: bool = Field(
        description="Comes with the website (system pages and the seeded legal pages): its "
        "slug and kind are fixed and it can't be deleted or archived"
    )
    block_count: int
    updated_at: datetime = Field(
        description="Send it back as expected_updated_at when saving, to detect someone "
        "else's save in between"
    )
    updated_by: UserRef | None


class Page(PageSummary):
    blocks: list[Block]
    media: list[Media] = Field(
        description="Library items the page uses, for previews: its blocks' files in order of "
        "first use, then the share image (seo.og_image_id) if not already listed"
    )
    seo: Seo
    og_image: Media | None = Field(description="The library image seo.og_image_id names")
    seo_warnings: list[SeoWarning]
    translations: Translations
    publish_blockers: list[str] = Field(
        description="Why it can't be published now (empty = ready); permissions aside"
    )
    created_at: datetime
    created_by: UserRef | None


class PageList(OutModel):
    items: list[PageSummary]
    meta: PageMeta


class PageInput(StrictModel):
    """A new draft page. System pages come with the site and can't be created."""

    slug: Annotated[Slug | None, BlankIsNone] = Field(
        default=None, description="Made from the title when left out"
    )
    title: Plain120
    kind: EditableKind
    publish_at: AwareDatetime | None = None
    unpublish_at: AwareDatetime | None = None
    show_in_nav: bool = False
    nav_order: NavOrder | None = None
    legal_version: Annotated[Plain20 | None, BlankIsNone] = Field(
        default=None, description="Legal pages only, e.g. 1.0", examples=["1.0"]
    )
    seo: Seo = Field(default_factory=Seo)
    translations: PageTranslations = Field(default_factory=Translations)


class PageUpdate(StrictModel):
    """PATCH: send only what changes. `publish_state: archived` archives, `draft` restores."""

    slug: Slug | None = None
    title: Plain120 | None = None
    kind: EditableKind | None = None
    publish_at: AwareDatetime | None = None
    unpublish_at: AwareDatetime | None = None
    show_in_nav: bool | None = None
    nav_order: NavOrder | None = None
    legal_version: Annotated[Plain20 | None, BlankIsNone] = None
    seo: Seo | None = None
    translations: PageTranslations | None = None
    publish_state: RestoreOrArchive | None = None
    expected_updated_at: AwareDatetime | None = Field(default=None, description=EXPECTED)

    _required = field_validator(
        "slug", "title", "kind", "show_in_nav", "seo", "translations", "publish_state"
    )(_not_null)


class PageBlocksInput(StrictModel):
    blocks: Annotated[list[BlockInput], Field(max_length=MAX_BLOCKS)] = Field(
        description="The full ordered list: blocks left out are deleted"
    )
    expected_updated_at: AwareDatetime | None = Field(default=None, description=EXPECTED)


# --- Posts -----------------------------------------------------------------------------------


def _tags(values: list[str]) -> list[str]:
    seen: set[str] = set()
    for value in values:
        if value.lower() in seen:
            raise PydanticCustomError("duplicates", "Each tag can appear only once.")
        seen.add(value.lower())
    return values


Tags = Annotated[list[Plain40], Field(max_length=MAX_TAGS), AfterValidator(_tags)]


class PostSummary(OutModel):
    """A row of the CMS posts list."""

    id: uuid.UUID
    slug: str
    path: str = Field(description="Address on the website: /blog/<slug>")
    title: str
    excerpt: str | None
    category: str | None
    tags: list[str]
    cover: Media | None
    author: UserRef | None
    publish_state: PublishState
    published_at: datetime | None = Field(description="First publish (the article's date)")
    is_sample: bool
    updated_at: datetime


class Post(PostSummary):
    body: str = Field(description="FormattedText")
    seo: Seo
    og_image: Media | None = Field(description="The library image seo.og_image_id names")
    seo_warnings: list[SeoWarning]
    translations: Translations
    publish_blockers: list[str]
    created_at: datetime
    updated_by: UserRef | None


class PostList(OutModel):
    items: list[PostSummary]
    meta: PageMeta


class PostInput(StrictModel):
    slug: Annotated[Slug | None, BlankIsNone] = Field(
        default=None, description="Made from the title when left out"
    )
    title: Plain160
    excerpt: Annotated[Plain300 | None, BlankIsNone] = None
    body: Formatted50000
    cover_media_id: uuid.UUID | None = Field(default=None, description="An image in the library")
    category: Annotated[Plain40 | None, BlankIsNone] = Field(
        default=None, examples=["Buying guide"]
    )
    tags: Tags = Field(default_factory=list)
    seo: Seo = Field(default_factory=Seo)
    translations: PostTranslations = Field(default_factory=Translations)


class PostUpdate(StrictModel):
    """PATCH: send only what changes. `publish_state: archived` archives, `draft` restores."""

    slug: Slug | None = None
    title: Plain160 | None = None
    excerpt: Annotated[Plain300 | None, BlankIsNone] = None
    body: Formatted50000 | None = None
    cover_media_id: uuid.UUID | None = None
    category: Annotated[Plain40 | None, BlankIsNone] = None
    tags: Tags | None = None
    seo: Seo | None = None
    translations: PostTranslations | None = None
    publish_state: RestoreOrArchive | None = None

    _required = field_validator(
        "slug", "title", "body", "tags", "seo", "translations", "publish_state"
    )(_not_null)
