"""The `BlockInput` and `Block` unions: one variant per block type, chosen by `type` (design
contract schemas BlockInput and Block).

Collaborators: blocks.py (the `*Data` shapes), page_blocks.py (saves), present.py (reads).

Contract deviation (D-035): Block and BlockInput are discriminated unions on `type`. Every variant
has the contract's fields (id, type, data, is_visible, and sort_order on Block); `data` is typed
per type instead of a free object, so the generated web client knows each form's fields.

WHY written out (not generated in a loop): mypy and the OpenAPI generator both need real classes
with names, and the names become the web client's types.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import Field, RootModel

from empire_api.content.blocks import (
    ColumnsData,
    CtaData,
    DividerData,
    FaqListData,
    GalleryData,
    GridData,
    HeroData,
    ImageData,
    LeadFormData,
    MapData,
    OfferBannerData,
    RichTextData,
    StatsData,
    StepsData,
    TestimonialsData,
    VideoData,
)
from empire_api.content.vocab import BLOCK_TYPES
from empire_api.errors import register_union_tags
from empire_api.projects.fields import OutModel, StrictModel

register_union_tags(BLOCK_TYPES)


class _InputBase(StrictModel):
    id: uuid.UUID | None = Field(default=None, description="Send it back for existing blocks")
    is_visible: bool = True


class _OutputBase(OutModel):
    id: uuid.UUID
    sort_order: int
    is_visible: bool


class HeroBlockInput(_InputBase):
    type: Literal["hero"]
    data: HeroData


class RichTextBlockInput(_InputBase):
    type: Literal["rich_text"]
    data: RichTextData


class ImageBlockInput(_InputBase):
    type: Literal["image"]
    data: ImageData


class GalleryBlockInput(_InputBase):
    type: Literal["gallery"]
    data: GalleryData


class VideoBlockInput(_InputBase):
    type: Literal["video"]
    data: VideoData


class ProjectGridBlockInput(_InputBase):
    type: Literal["project_grid"]
    data: GridData


class PropertyGridBlockInput(_InputBase):
    type: Literal["property_grid"]
    data: GridData


class CtaBlockInput(_InputBase):
    type: Literal["cta"]
    data: CtaData


class LeadFormBlockInput(_InputBase):
    type: Literal["lead_form"]
    data: LeadFormData


class FaqListBlockInput(_InputBase):
    type: Literal["faq_list"]
    data: FaqListData


class StatsBlockInput(_InputBase):
    type: Literal["stats"]
    data: StatsData


class TestimonialsBlockInput(_InputBase):
    type: Literal["testimonials"]
    data: TestimonialsData


class OfferBannerBlockInput(_InputBase):
    type: Literal["offer_banner"]
    data: OfferBannerData


class MapBlockInput(_InputBase):
    type: Literal["map"]
    data: MapData


class StepsBlockInput(_InputBase):
    type: Literal["steps"]
    data: StepsData


class ColumnsBlockInput(_InputBase):
    type: Literal["columns"]
    data: ColumnsData


class DividerBlockInput(_InputBase):
    type: Literal["divider"]
    data: DividerData = Field(default_factory=DividerData)


class HeroBlock(_OutputBase):
    type: Literal["hero"]
    data: HeroData


class RichTextBlock(_OutputBase):
    type: Literal["rich_text"]
    data: RichTextData


class ImageBlock(_OutputBase):
    type: Literal["image"]
    data: ImageData


class GalleryBlock(_OutputBase):
    type: Literal["gallery"]
    data: GalleryData


class VideoBlock(_OutputBase):
    type: Literal["video"]
    data: VideoData


class ProjectGridBlock(_OutputBase):
    type: Literal["project_grid"]
    data: GridData


class PropertyGridBlock(_OutputBase):
    type: Literal["property_grid"]
    data: GridData


class CtaBlock(_OutputBase):
    type: Literal["cta"]
    data: CtaData


class LeadFormBlock(_OutputBase):
    type: Literal["lead_form"]
    data: LeadFormData


class FaqListBlock(_OutputBase):
    type: Literal["faq_list"]
    data: FaqListData


class StatsBlock(_OutputBase):
    type: Literal["stats"]
    data: StatsData


class TestimonialsBlock(_OutputBase):
    type: Literal["testimonials"]
    data: TestimonialsData


class OfferBannerBlock(_OutputBase):
    type: Literal["offer_banner"]
    data: OfferBannerData


class MapBlock(_OutputBase):
    type: Literal["map"]
    data: MapData


class StepsBlock(_OutputBase):
    type: Literal["steps"]
    data: StepsData


class ColumnsBlock(_OutputBase):
    type: Literal["columns"]
    data: ColumnsData


class DividerBlock(_OutputBase):
    type: Literal["divider"]
    data: DividerData


AnyBlockInput = Annotated[
    HeroBlockInput
    | RichTextBlockInput
    | ImageBlockInput
    | GalleryBlockInput
    | VideoBlockInput
    | ProjectGridBlockInput
    | PropertyGridBlockInput
    | CtaBlockInput
    | LeadFormBlockInput
    | FaqListBlockInput
    | StatsBlockInput
    | TestimonialsBlockInput
    | OfferBannerBlockInput
    | MapBlockInput
    | StepsBlockInput
    | ColumnsBlockInput
    | DividerBlockInput,
    Field(discriminator="type"),
]
AnyBlock = Annotated[
    HeroBlock
    | RichTextBlock
    | ImageBlock
    | GalleryBlock
    | VideoBlock
    | ProjectGridBlock
    | PropertyGridBlock
    | CtaBlock
    | LeadFormBlock
    | FaqListBlock
    | StatsBlock
    | TestimonialsBlock
    | OfferBannerBlock
    | MapBlock
    | StepsBlock
    | ColumnsBlock
    | DividerBlock,
    Field(discriminator="type"),
]


class BlockInput(RootModel[AnyBlockInput]):
    """One block as the editor sends it; `data` is checked against its `type`'s shape."""


class Block(RootModel[AnyBlock]):
    """A saved block; `data` has the shape of its `type`."""
