"""What decides whether a page or post may go on the website: the draft-text check for legal
pages and the publish blockers; which legal pages need `legal.publish` for any change; plus the
messages the services share.

Collaborators: pages.py and posts.py (publish refuses with 409 while blockers remain),
page_blocks.py and pages.py (edits of guarded legal pages, draft text on live legal pages),
schedule.py (a scheduled publish that is blocked is cancelled and audited), present.py
(`publish_blockers` and `is_draft_text` on the CMS views).
Implements: D-015 (no sample data on the live site), D-017 (legal text is a Claude draft until
the owner approves it), ARCHITECTURE §6.

COMPLIANCE: don't remove or weaken a blocker without the owner's approval.
COMPLIANCE (D-017, review H2 and M1):
  - A legal page that is live or scheduled is guarded: any change needs `legal.publish`, so the
    wording the tick publishes is the wording a `legal.publish` holder scheduled.
  - In production a live legal page never carries the [DRAFT mark: an edit that would leave it
    there is refused (409), and so is moving draft text into or out of the legal kind (which
    would otherwise let it go live as a "standard" page and come back as legal). Development
    and tests allow both, as they allow publishing draft text, so the CMS can be tried out.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any, Final

from empire_api.content.common import has_draft_mark, is_production
from empire_api.content.models import Page, Post
from empire_api.errors import ApiProblem

SAMPLE_ON_LIVE_SITE: Final = "Sample data can't be published on the live site"
LEGAL_DRAFT: Final = (
    "The legal text is still a draft: replace the [DRAFT …] text with the wording the owner "
    "approved (D-017)"
)
LEGAL_ONLY: Final = "Only admins can change or publish legal pages (legal.publish)."
NOT_ALLOWED_OFF_SITE: Final = "Your role can't take a published page off the website."
NO_SCHEDULE_RIGHTS: Final = "Your role can't schedule publishing (content.publish)."
NO_SEO_RIGHTS: Final = "Your role can't change SEO fields (seo.manage)."


def text_has_draft_mark(title: str, block_data: Iterable[Mapping[str, Any]]) -> bool:
    """COMPLIANCE (D-017): the title or any block's text still carries a [DRAFT mark."""
    texts = [json.dumps(data, ensure_ascii=False) for data in block_data]
    return has_draft_mark(title, *texts)


def is_draft_text(page: Page) -> bool:
    """COMPLIANCE (D-017): a legal page whose title or block text still carries a [DRAFT mark.

    Other kinds never count as draft text: the mark is the legal-text approval workflow.
    """
    if page.kind != "legal":
        return False
    return text_has_draft_mark(page.title, (block.data for block in page.blocks))


def legal_guarded(page: Page) -> bool:
    """COMPLIANCE (module header, review H2): a legal page that is live, or scheduled to go
    live (`publish_at` set), needs `legal.publish` for any change."""
    return page.kind == "legal" and (
        page.publish_state == "published" or page.publish_at is not None
    )


def leaves_draft_text_live(
    kind: str, publish_state: str, title: str, block_data: Iterable[Mapping[str, Any]]
) -> bool:
    """COMPLIANCE (module header, review M1): in production, whether a page in this state
    would be a live legal page carrying the [DRAFT mark."""
    return (
        is_production()
        and kind == "legal"
        and publish_state == "published"
        and text_has_draft_mark(title, block_data)
    )


def moves_draft_text(
    kind_before: str, kind_after: str, title: str, block_data: Iterable[Mapping[str, Any]]
) -> bool:
    """COMPLIANCE (module header, review M1): in production, whether a kind change into or out
    of `legal` would carry [DRAFT text with it."""
    crosses = kind_before != kind_after and "legal" in (kind_before, kind_after)
    return is_production() and crosses and text_has_draft_mark(title, block_data)


def legal_draft_conflict(field: str) -> ApiProblem:
    """The 409 for draft legal text that would be (or stay) live; `field` is what to change."""
    return ApiProblem(
        409,
        LEGAL_DRAFT + ".",
        title="Legal text still a draft",
        errors=[{"field": field, "message": LEGAL_DRAFT}],
    )


def page_blockers(page: Page) -> list[str]:
    """Every reason the page can't be published now (empty = ready). Permissions aside."""
    blockers: list[str] = []
    if page.is_sample and is_production():
        blockers.append(SAMPLE_ON_LIVE_SITE)
    if is_production() and is_draft_text(page):
        blockers.append(LEGAL_DRAFT)
    return blockers


def post_blockers(post: Post) -> list[str]:
    return [SAMPLE_ON_LIVE_SITE] if post.is_sample and is_production() else []
