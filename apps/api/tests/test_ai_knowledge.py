"""Task 7.1 (D-059): the knowledge index, its outbox consumer, the daily guard and the providers.

Index tests need pgvector (CI's database has it; locally see SETUP "pgvector"); they skip
without it. The provider tests need no database.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from conftest import SignedIn
from content_support import FAQS, block, create_faq, create_page, publish_page, put_blocks
from empire_api.ai import handlers, indexer, knowledge, store
from empire_api.ai.models import AiUsageDay
from empire_api.ai.providers import get_provider
from empire_api.ai.providers.base import EMBEDDING_DIMENSIONS, ProviderBusyError, ProviderError
from empire_api.ai.providers.cloudflare import CloudflareProvider
from empire_api.ai.providers.fake import FakeProvider
from empire_api.cli import app as cli_app
from empire_api.config import get_settings
from empire_api.content.models import Page
from empire_api.content.seed import seed_pages
from empire_api.integrations import outbox_drain
from empire_api.integrations.handlers import PermanentDeliveryError, handlers_for
from empire_api.platform.models import OutboxEvent
from empire_api.projects.models import Project
from projects_support import (
    PROJECTS,
    add_configuration,
    create_project,
    make_ready,
    ok,
    patch_project,
    publish,
)

RERA = "UPRERAPRJ-TEST-01"  # what make_ready sets


def drain() -> None:
    """Deliver until nothing due is left (content events queue `ai.reindex` events)."""
    for _ in range(10):
        if outbox_drain.drain().processed == 0:
            return


def _pgvector(db: Session) -> bool:
    return store.available(db)


@pytest.fixture
def ai_on(monkeypatch: pytest.MonkeyPatch, db: Session) -> Iterator[FakeProvider]:
    if not _pgvector(db):
        pytest.skip("pgvector isn't installed in the test database (SETUP: pgvector)")
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    get_provider.cache_clear()
    provider = get_provider()
    assert isinstance(provider, FakeProvider)
    yield provider
    get_settings.cache_clear()
    get_provider.cache_clear()


def chunks(db: Session, source_type: str = "project") -> list[Any]:
    db.expire_all()
    return list(
        db.execute(
            text(
                "SELECT url, title, body, position FROM knowledge_chunk WHERE source_type = :t"
                " ORDER BY url, position"
            ),
            {"t": source_type},
        )
    )


def live_project(owner: SignedIn, **fields: Any) -> dict[str, Any]:
    project: dict[str, Any] = create_project(owner, **fields)
    make_ready(owner, project["id"])
    ok(publish(owner, project["id"]))
    return project


# ── Off by default ───────────────────────────────────────────────────────────────────────


def test_ai_is_off_without_a_provider(owner: SignedIn, db: Session, qr_present: None) -> None:
    get_provider.cache_clear()
    assert get_settings().ai_provider == ""
    assert get_provider() is None
    live_project(owner)
    drain()
    if _pgvector(db):
        assert chunks(db) == []
    assert db.scalars(select(AiUsageDay)).all() == []
    assert all(e.status == "delivered" for e in db.scalars(select(OutboxEvent)))


def test_cloudflare_needs_its_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "cloudflare")
    get_settings.cache_clear()
    get_provider.cache_clear()
    try:
        assert get_provider() is None  # no account id or token: stays off
    finally:
        get_settings.cache_clear()
        get_provider.cache_clear()


def test_content_events_are_consumed() -> None:
    for event_type in (
        "project.published",
        "project.unpublished",
        "construction_update.published",
        "page.published",
        "faq.changed",
        "offer.ended",
        "testimonial.changed",
    ):
        assert handlers.queue_reindex in handlers_for(event_type)
    assert handlers.reindex in handlers_for(handlers.REINDEX_EVENT)


# ── What gets indexed ─────────────────────────────────────────────────────────────────────


def test_publish_indexes_live_text_and_unpublish_removes_it(
    owner: SignedIn, db: Session, qr_present: None, ai_on: FakeProvider
) -> None:
    project = create_project(owner, name="Aurum Heights")
    ok(patch_project(owner, project["id"], {"description": "Close to the metro and a park."}))
    make_ready(owner, project["id"])
    drain()
    assert chunks(db) == []  # a draft is never indexed

    ok(publish(owner, project["id"]))
    drain()
    rows = chunks(db)
    assert rows, "the live project should be indexed"
    assert {r.url for r in rows} == {"/projects/aurum-heights"}
    assert rows[0].title == "Aurum Heights"
    body = "\n".join(r.body for r in rows)
    assert "Close to the metro and a park." in body
    assert "2 BHK" in body
    assert store.neurons_today(db) > 0

    url = f"{PROJECTS}/{project['id']}/unpublish"
    ok(owner.client.post(url, headers=owner.headers()))
    drain()
    assert chunks(db) == []


def test_chunks_never_hold_prices_or_rera_numbers(
    owner: SignedIn, db: Session, qr_present: None, ai_on: FakeProvider
) -> None:
    """COMPLIANCE (D-059): the model can't repeat what it was never given."""
    project = create_project(owner, name="Price Check")
    make_ready(owner, project["id"])
    price = {"min_inr": 8_512_345, "max_inr": 12_534_567, "rate_inr": 7_123, "rate_unit": "sqft"}
    add_configuration(owner, project["id"], name="3 BHK", price=price)
    ok(publish(owner, project["id"]))
    drain()
    body = "\n".join(r.body for r in chunks(db))
    assert "3 BHK" in body
    assert RERA not in body
    assert "rera" not in body.lower()
    for needle in ("8512345", "85,12,345", "12534567", "7123", "7,123", "₹", " L ", " Cr"):
        assert needle not in body, needle


def test_lines_skip_ids_links_media_prices_and_rera() -> None:
    data = {
        "id": "x",
        "name": "Kept",
        "rera_number": "UPRERAPRJ1",
        "project_rera": {"number": "N"},
        "price": {"display": "₹ 85 L"},
        "configurations": [{"name": "2 BHK", "carpet_area_sqft": 650, "cover_id": "m"}],
        "brochure_url": "https://x",
        "is_ready": True,
        "is_hidden": False,
    }
    lines = list(knowledge._lines(data))
    assert lines == [
        "name: Kept",
        "configurations: name: 2 BHK; carpet area sqft: 650",
        "is ready: yes",
    ]


def test_long_text_is_split_with_the_title_on_every_chunk() -> None:
    lines = [f"line {i}: " + "word " * 40 for i in range(30)]
    out = knowledge._chunks("page", uuid.uuid4(), "/about", "About us", lines)
    assert len(out) > 1
    assert all(len(c.body) <= knowledge.CHUNK_CHARS for c in out)
    assert all(c.body.startswith("About us") for c in out)
    assert [c.position for c in out] == list(range(len(out)))
    assert len({c.content_hash for c in out}) == len(out)


# ── Re-indexing costs ──────────────────────────────────────────────────────────────────────


def test_unchanged_text_is_not_embedded_again(
    owner: SignedIn, db: Session, qr_present: None, ai_on: FakeProvider
) -> None:
    project = live_project(owner)
    drain()
    embeds = [c for c in ai_on.calls if c.startswith("embed")]
    assert embeds
    project_id = uuid.UUID(project["id"])
    result = indexer.reindex_source(db, ai_on, "project", project_id)
    db.commit()
    assert (result.unchanged, result.indexed) == (1, 0)
    assert [c for c in ai_on.calls if c.startswith("embed")] == embeds

    ok(patch_project(owner, project["id"], {"description": "Now with a club house."}))
    drain()
    assert len([c for c in ai_on.calls if c.startswith("embed")]) == len(embeds) + 1
    assert "Now with a club house." in "\n".join(r.body for r in chunks(db))


def test_reindex_all_drops_chunks_of_items_that_are_gone(
    owner: SignedIn, db: Session, qr_present: None, ai_on: FakeProvider
) -> None:
    live_project(owner)
    drain()
    ghost = uuid.uuid4()
    chunk = knowledge._chunks("post", ghost, "/blog/gone", "Gone", ["text: old"])
    store.insert_chunks(db, chunk, ai_on.embed([c.body for c in chunk]))
    db.commit()
    result = indexer.reindex_all(db, ai_on)
    assert result.removed == 1
    assert result.unchanged >= 1
    assert chunks(db, "post") == []
    assert chunks(db, "project")


def test_the_daily_guard_stops_indexing_and_the_event_is_retried(
    owner: SignedIn, db: Session, qr_present: None, ai_on: FakeProvider
) -> None:
    store.add_usage(db, neurons=get_settings().ai_daily_neuron_guard)
    db.commit()
    project = live_project(owner)
    drain()
    assert chunks(db) == []
    db.expire_all()
    published = db.scalars(select(OutboxEvent).where(OutboxEvent.type == "project.published"))
    assert published.one().status == "delivered"  # the content event (revalidation) never waits
    row = db.scalars(select(OutboxEvent).where(OutboxEvent.type == "ai.reindex")).one()
    assert row.status == "pending"  # retried later, not dead
    assert row.last_error == "RuntimeError: ai_busy_daily_guard"
    with pytest.raises(ProviderBusyError):
        indexer.reindex_source(db, ai_on, "project", uuid.UUID(project["id"]))


def test_a_refused_request_is_dead_at_once(
    db: Session, ai_on: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise ProviderError("cf_400")

    monkeypatch.setattr(indexer, "reindex_source", refuse)
    event = OutboxEvent(
        type="ai.reindex",
        aggregate_type="page",
        aggregate_id=str(uuid.uuid4()),
        payload={"source_type": "page", "source_id": str(uuid.uuid4())},
    )
    with pytest.raises(PermanentDeliveryError, match="ai_refused_cf_400"):
        handlers.reindex(db, event)


def test_event_targets(db: Session) -> None:
    project_id = uuid.uuid4()
    child = OutboxEvent(
        type="configuration.changed",
        aggregate_type="configuration",
        aggregate_id=str(uuid.uuid4()),
        payload={"project_id": str(project_id)},
    )
    assert handlers._targets(db, child) == [("project", project_id)]  # no pages yet
    faq = OutboxEvent(
        type="faq.changed", aggregate_type="faq", aggregate_id=str(uuid.uuid4()), payload={}
    )
    seed_pages(db)
    db.commit()
    page_ids = set(db.scalars(select(Page.id)))
    targets = handlers._targets(db, faq)
    assert page_ids and {kind for kind, _ in targets} == {"page"}
    assert {source_id for _, source_id in targets} == page_ids
    pages = sorted(("page", i) for i in page_ids)
    assert sorted(handlers._targets(db, child)) == sorted([("project", project_id), *pages])
    for kind in ("offer.ended", "testimonial.changed"):
        wide = OutboxEvent(type=kind, aggregate_type="x", aggregate_id="1", payload={})
        assert sorted(handlers._targets(db, wide)) == pages
    other = OutboxEvent(
        type="post.published", aggregate_type="post", aggregate_id="bad", payload={}
    )
    assert handlers._targets(db, other) == []


# ── Search and counts ──────────────────────────────────────────────────────────────────────


def test_search_finds_the_nearest_chunk_and_prefers_the_current_page(
    db: Session, ai_on: FakeProvider
) -> None:
    a = knowledge._chunks("page", uuid.uuid4(), "/a", "A", ["text: swimming pool and gym"])
    b = knowledge._chunks("page", uuid.uuid4(), "/b", "B", ["text: metro station nearby"])
    store.insert_chunks(db, a + b, ai_on.embed([c.body for c in a + b]))
    db.commit()
    query = ai_on.embed(["is there a swimming pool"])[0]
    hits = store.search(db, query, limit=2)
    assert [h.url for h in hits] == ["/a", "/b"]
    close = ai_on.embed(["A B text"])[0]
    assert store.search(db, close, limit=1, prefer_url="/b")[0].url == "/b"


def test_usage_adds_up_per_day(db: Session) -> None:
    store.add_usage(db, neurons=1.5, answers=1)
    store.add_usage(db, neurons=2.25, busy=1)
    store.add_usage(db, neurons=0, no_answer=1)
    db.commit()
    row = db.scalars(select(AiUsageDay)).one()
    assert (row.answers, row.busy, row.no_answer) == (1, 1, 1)
    assert float(row.neurons) == 3.75
    assert float(store.neurons_today(db)) == 3.75


def test_cli_reindex_and_status(
    owner: SignedIn, db: Session, qr_present: None, ai_on: FakeProvider
) -> None:
    project = live_project(owner)
    db.execute(text("TRUNCATE knowledge_chunk"))
    db.commit()
    runner = CliRunner()
    result = runner.invoke(cli_app, ["ai", "reindex"])
    assert result.exit_code == 0, result.output
    assert "Indexed 1 items" in result.output
    assert db.get(Project, uuid.UUID(project["id"])) is not None
    assert chunks(db)
    status = runner.invoke(cli_app, ["ai", "status"])
    assert status.exit_code == 0
    assert "Provider: fake" in status.output


def test_cli_reindex_refuses_while_ai_is_off() -> None:
    get_provider.cache_clear()
    result = CliRunner().invoke(cli_app, ["ai", "reindex"])
    assert result.exit_code == 1
    assert "AI is off" in result.output


# ── Cloudflare client (no network) ────────────────────────────────────────────────────────

TOKEN = "cf-test-token-not-real"


def cloudflare(handler: Any) -> tuple[CloudflareProvider, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        result: httpx.Response = handler(request)
        return result

    provider = CloudflareProvider(
        "acc123",
        TOKEN,
        chat_model="@cf/qwen/qwen3-30b-a3b-fp8",
        embed_model="@cf/baai/bge-m3",
        client_factory=lambda timeout: httpx.Client(transport=httpx.MockTransport(record)),
    )
    return provider, seen


def test_cloudflare_embed_and_chat_shapes() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/run/@cf/baai/bge-m3"):
            texts = json.loads(request.content)["text"]
            vectors = [[0.1] * EMBEDDING_DIMENSIONS for _ in texts]
            return httpx.Response(200, json={"success": True, "result": {"data": vectors}})
        body = {
            "choices": [{"message": {"role": "assistant", "content": "Yes [1]"}}],
            "usage": {"prompt_tokens": 2300, "completion_tokens": 40},
        }
        return httpx.Response(200, json=body)

    provider, seen = cloudflare(answer)
    assert len(provider.embed(["a", "b"])) == 2
    result = provider.chat([{"role": "user", "content": "q"}], max_tokens=300)
    assert (result.text, result.prompt_tokens, result.completion_tokens) == ("Yes [1]", 2300, 40)
    embed, chat = seen
    assert str(embed.url) == (
        "https://api.cloudflare.com/client/v4/accounts/acc123/ai/run/@cf/baai/bge-m3"
    )
    assert str(chat.url).endswith("/accounts/acc123/ai/v1/chat/completions")
    assert json.loads(chat.content)["model"] == "@cf/qwen/qwen3-30b-a3b-fp8"
    for request in seen:  # SECURITY: the token only in the Authorization header
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        assert TOKEN not in str(request.url)
        assert TOKEN.encode() not in request.content
    assert TOKEN not in repr(provider)


@pytest.mark.parametrize(
    ("status", "body", "error", "code"),
    [
        (429, {"errors": [{"code": 3040, "message": "x"}]}, ProviderBusyError, "cf_3040"),
        (503, {}, ProviderBusyError, "cf_http_503"),
        (400, {"errors": [{"code": 3036}]}, ProviderBusyError, "cf_3036"),
        (400, {"errors": [{"code": 5006}]}, ProviderError, "cf_5006"),
        (401, "not json", ProviderError, "cf_http_401"),
    ],
)
def test_cloudflare_errors_are_codes(status: int, body: Any, error: type, code: str) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        if isinstance(body, str):
            return httpx.Response(status, text=body)
        return httpx.Response(status, json=body)

    provider, _ = cloudflare(fail)
    with pytest.raises(error) as caught:
        provider.chat([{"role": "user", "content": "secret question"}], max_tokens=10)
    assert str(caught.value) == code
    assert TOKEN not in str(caught.value)


def test_cloudflare_timeouts_and_bad_shapes() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    provider, _ = cloudflare(slow)
    with pytest.raises(ProviderBusyError, match="cf_timeout"):
        provider.chat([{"role": "user", "content": "q"}], max_tokens=10)

    def short(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": {"data": [[0.1, 0.2]]}})

    provider, _ = cloudflare(short)
    with pytest.raises(ProviderError, match="cf_embedding_shape"):
        provider.embed(["a"])
    with pytest.raises(ProviderError, match="cf_chat_shape"):
        provider.chat([{"role": "user", "content": "q"}], max_tokens=10)


def test_pages_and_faqs_are_indexed_and_follow_faq_changes(
    owner: SignedIn, db: Session, qr_present: None, ai_on: FakeProvider
) -> None:
    faq = create_faq(owner, "Is parking included?", answer="One covered space per flat.")
    page = create_page(owner, "Buying guide")
    put_blocks(
        owner,
        page["id"],
        [
            block("rich_text", {"body": "We help you *check* a project before you book."}),
            block("faq_list", {"faq_ids": [faq["id"]]}),
        ],
    )
    ok(publish_page(owner, page["id"]))
    drain()
    rows = chunks(db, "page")
    assert {r.url for r in rows} == {f"/{page['slug']}"}
    body = "\n".join(r.body for r in rows)
    assert "check* a project before you book" in body
    assert "Is parking included?" in body
    assert "One covered space per flat." in body

    url = f"{FAQS}/{faq['id']}"
    ok(owner.client.patch(url, json={"answer": "Two spaces."}, headers=owner.headers()))
    drain()
    body = "\n".join(r.body for r in chunks(db, "page"))
    assert "Two spaces." in body
    assert "One covered space" not in body

    project = live_project(owner)
    create_faq(owner, "Lift backup?", answer="Yes, full power backup.", project_id=project["id"])
    drain()
    assert "Yes, full power backup." in "\n".join(r.body for r in chunks(db, "project"))


def test_free_text_prices_and_registration_numbers_are_redacted(
    owner: SignedIn, db: Session, qr_present: None, ai_on: FakeProvider
) -> None:
    """COMPLIANCE (D-059): free text is scrubbed by value, not only by field name."""
    project = create_project(owner, name="Free Text")
    text_ = "From ₹45 L onwards, Rs 6,500 per sq ft, 1.2 Cr villas. UP RERA No: UPRERAPRJ778899."
    ok(patch_project(owner, project["id"], {"description": text_}))
    make_ready(owner, project["id"])
    ok(publish(owner, project["id"]))
    drain()
    body = "\n".join(r.body for r in chunks(db))
    assert "onwards" in body
    for needle in ("45 L", "6,500", "1.2 Cr", "778899", "UPRERAPRJ"):
        assert needle not in body, needle


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("From ₹45 L onwards", "From [see the project page] onwards"),
        ("Rs. 1,25,00,000 all in", "[see the project page] all in"),
        ("starting 85 lakh", "starting [see the project page]"),
        ("45 लाख से", "[see the project page] से"),
        ("6500 per sq. ft.", "[see the project page]."),
        ("RERA registration PRJ/2024/55", "RERA registration [see the project page]"),
        ("registered with UP-RERA", "registered with UP-RERA"),
        ("carpet area 650 sq ft, 2 BHK", "carpet area 650 sq ft, 2 BHK"),
    ],
)
def test_redact(line: str, expected: str) -> None:
    assert knowledge.redact(line) == expected


def test_pages_drop_a_project_when_it_is_unpublished(
    owner: SignedIn, db: Session, qr_present: None, ai_on: FakeProvider
) -> None:
    project = live_project(owner, name="Gone Soon Towers")
    page = create_page(owner, "Our projects map")
    put_blocks(owner, page["id"], [block("map", {"project_id": project["id"]})])
    ok(publish_page(owner, page["id"]))
    drain()
    assert "Gone Soon Towers" in "\n".join(r.body for r in chunks(db, "page"))

    url = f"{PROJECTS}/{project['id']}/unpublish"
    ok(owner.client.post(url, headers=owner.headers()))
    drain()
    assert "Gone Soon Towers" not in "\n".join(r.body for r in chunks(db, "page"))
    assert chunks(db, "project") == []


def test_the_daily_clean_up_queues_everything_once(
    owner: SignedIn, db: Session, qr_present: None, ai_on: FakeProvider
) -> None:
    live_project(owner)
    drain()
    embeds = len([c for c in ai_on.calls if c.startswith("embed")])
    counts = outbox_drain.cleanup()
    assert counts["ai_reindex_queued"] >= 1
    drain()
    db.expire_all()
    reindex = db.scalars(select(OutboxEvent).where(OutboxEvent.type == "ai.reindex")).all()
    assert all(e.status == "delivered" for e in reindex)
    assert len([c for c in ai_on.calls if c.startswith("embed")]) == embeds  # unchanged: free
