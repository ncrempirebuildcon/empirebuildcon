"""`empire-api golive-check`: is this database ready to be the live site? (RUNBOOK §4, task L8)

Run against staging while the content goes in (L5–L7), and against production before DNS points
at it. It reads only, and prints one line per check: PASS, WARN (look at it) or FAIL (blocks
go-live). Exit code 1 when anything fails.

It judges content the way a visitor sees it: through the public API's own builders, which
already hide drafts, scheduled items and (in production) sample data. So "live" here means
exactly what the website would show.

COMPLIANCE: the checks mirror the hard rules: RERA number, QR and up-rera.in on every project
(D-002); no sample data on the live site (D-015); approved legal and consent texts (D-017,
D-034); no "[placeholder]" text left on a live page (AGENTS.md "Honest content").
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Final, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from empire_api.ai.providers import get_provider
from empire_api.config import get_settings
from empire_api.content import consent, page_rules
from empire_api.content.models import Page, Post
from empire_api.mail.handlers import sales_inbox
from empire_api.platform.models import OutboxEvent
from empire_api.projects.blockers import publish_blockers_for
from empire_api.projects.models import Project
from empire_api.public import service as public
from empire_api.site_settings.flags import is_enabled
from empire_api.site_settings.groups import LeadRoutingSettings
from empire_api.site_settings.service import read_typed
from empire_api.timeutil import utcnow
from empire_api.users.models import User

Status = Literal["PASS", "WARN", "FAIL"]

# Consent texts every enquiry form needs from day one (D-034). "cookies" and "chat" are checked
# only when what uses them is switched on.
LAUNCH_CONSENTS: Final = ("lead_form", "marketing", "brochure")
# "[Office address]", "[DRAFT …]", "[TBD]": text in square brackets that starts like a note to
# fill in. A Markdown link "[text](url)" isn't one.
_PLACEHOLDER: Final = re.compile(
    r"\[(?:DRAFT|TBD|TODO|placeholder|[A-Z][a-z]+(?: [a-z]+){0,5})[^\]\n]{0,80}\](?!\()"
)
STUCK_AFTER: Final = timedelta(minutes=45)  # the sweep runs every 15 minutes
DEAD_WINDOW: Final = timedelta(days=7)


@dataclass(frozen=True)
class Check:
    status: Status
    name: str
    detail: str


def _placeholders(text: str) -> list[str]:
    return sorted(set(_PLACEHOLDER.findall(text)))


def _live_projects(db: Session) -> list[tuple[Project, str]]:
    out = []
    for project in db.scalars(select(Project).order_by(Project.name)):
        detail = public.get_public_project(db, project.slug)
        if detail is not None:
            out.append((project, detail.model_dump_json()))
    return out


def _live_pages(db: Session) -> list[tuple[Page, str]]:
    out = []
    for page in db.scalars(select(Page).order_by(Page.slug)):
        detail = public.get_public_page(db, page.slug)
        if detail is not None:
            out.append((page, detail.model_dump_json()))
    return out


def _live_posts(db: Session) -> list[tuple[Post, str]]:
    out = []
    for post in db.scalars(select(Post).order_by(Post.slug)):
        detail = public.get_public_post(db, post.slug)
        if detail is not None:
            out.append((post, detail.model_dump_json()))
    return out


def check_projects(db: Session) -> list[Check]:
    live = _live_projects(db)
    if not live:
        return [Check("FAIL", "projects", "No project is live on the website yet (L5).")]
    checks = [Check("PASS", "projects", f"{len(live)} project(s) live.")]
    blockers = publish_blockers_for(db, [p for p, _ in live])
    for project, text in live:
        problems = [b.message for b in blockers.get(project.id, [])]
        if problems:
            checks.append(Check("FAIL", f"project {project.slug}", "; ".join(problems)))
        if found := _placeholders(text):
            checks.append(
                Check("FAIL", f"project {project.slug}", "Placeholder text: " + ", ".join(found))
            )
    return checks


def check_pages_and_posts(db: Session) -> list[Check]:
    checks: list[Check] = []
    pages = _live_pages(db)
    for page, text in pages:
        if page_rules.is_draft_text(page) or "[DRAFT" in text:
            checks.append(Check("FAIL", f"page /{page.slug}", "Still marked [DRAFT] (L6)."))
        elif found := _placeholders(text):
            checks.append(
                Check("FAIL", f"page /{page.slug}", "Placeholder text: " + ", ".join(found))
            )
    live_slugs = {page.slug for page, _ in pages}
    for page in db.scalars(select(Page).where(Page.kind == "legal").order_by(Page.slug)):
        if page.slug not in live_slugs:
            checks.append(Check("FAIL", f"page /{page.slug}", "Legal page isn't published (L6)."))
    for post, text in _live_posts(db):
        if found := _placeholders(text):
            checks.append(
                Check("FAIL", f"post /blog/{post.slug}", "Placeholder text: " + ", ".join(found))
            )
    if not checks:
        checks.append(Check("PASS", "pages", f"{len(pages)} live page(s); legal pages approved."))
    return checks


def check_site(db: Session) -> list[Check]:
    site = public.get_public_site(db)
    company = site.company
    checks: list[Check] = []
    missing = [
        label
        for label, value in (
            ("phone", company.phones),
            ("email", company.emails),
            ("address", company.address),
            ("WhatsApp", company.whatsapp),
        )
        if not value
    ]
    if missing:
        checks.append(Check("FAIL", "contact details", "Missing: " + ", ".join(missing) + "."))
    if found := _placeholders(company.model_dump_json()):
        checks.append(Check("FAIL", "contact details", "Placeholder text: " + ", ".join(found)))
    if not missing and not checks:
        checks.append(Check("PASS", "contact details", "Phone, email, address and WhatsApp set."))
    if site.has_sample:
        checks.append(Check("FAIL", "sample data", "The website still shows sample data (D-015)."))
    else:
        checks.append(Check("PASS", "sample data", "No sample data shown."))
    return checks


def check_consent(db: Session) -> list[Check]:
    kinds = list(LAUNCH_CONSENTS)
    if is_enabled(db, "chat_widget"):
        kinds.append("chat")
    site = public.get_public_site(db)
    if site.tracking is not None and any(
        getattr(site.tracking, f, None) for f in type(site.tracking).model_fields
    ):
        kinds.append("cookies")
    checks: list[Check] = []
    for kind in kinds:
        text = consent.current_text(db, kind)
        if text is None:
            checks.append(Check("FAIL", f"consent {kind}", "No published text (L6, D-034)."))
        elif consent.is_draft(text):
            checks.append(Check("FAIL", f"consent {kind}", f"Version {text.version} is a draft."))
        else:
            checks.append(Check("PASS", f"consent {kind}", f"Version {text.version} published."))
    return checks


def check_people(db: Session) -> list[Check]:
    checks: list[Check] = []
    admins = list(
        db.scalars(
            select(User).where(User.is_active.is_(True), User.role.in_(("super_admin", "admin")))
        )
    )
    supers = [u for u in admins if u.role == "super_admin"]
    if any(u.two_factor_enabled for u in supers):
        checks.append(Check("PASS", "super-admin", "At least one uses two-factor sign-in."))
    else:
        checks.append(
            Check("FAIL", "super-admin", "No active super-admin with two-factor sign-in.")
        )
    without = sorted(u.email for u in admins if not u.two_factor_enabled)
    if without:
        checks.append(
            Check(
                "WARN",
                "two-factor",
                f"{len(without)} admin(s) without two-factor: " + ", ".join(without),
            )
        )
    routing = read_typed(db, "lead_routing", LeadRoutingSettings)
    if routing.inbox_email:
        checks.append(Check("PASS", "lead alerts", f"Sent to {routing.inbox_email}."))
    else:
        to = ", ".join(sales_inbox(db)) or "nobody"
        checks.append(
            Check("WARN", "lead alerts", f"No shared sales inbox set; alerts go to {to} (D-050).")
        )
    return checks


def check_features(db: Session) -> list[Check]:
    checks: list[Check] = []
    if is_enabled(db, "chat_widget") and get_provider() is None:
        checks.append(
            Check("FAIL", "chat_widget", "On, but AI_PROVIDER is empty: every answer is 'busy'.")
        )
    elif is_enabled(db, "chat_widget"):
        checks.append(Check("WARN", "chat_widget", "On: only after the 7.4 dry run (RUNBOOK §6d)."))
    else:
        checks.append(Check("PASS", "chat_widget", "Off (launch state)."))
    return checks


def check_outbox(db: Session) -> list[Check]:
    now = utcnow()
    stuck = db.scalar(
        select(func.count())
        .select_from(OutboxEvent)
        .where(OutboxEvent.status == "pending", OutboxEvent.available_at < now - STUCK_AFTER)
    )
    dead = db.scalar(
        select(func.count())
        .select_from(OutboxEvent)
        .where(OutboxEvent.status == "dead", OutboxEvent.occurred_at > now - DEAD_WINDOW)
    )
    checks: list[Check] = []
    if stuck:
        checks.append(
            Check(
                "FAIL",
                "background job",
                f"{stuck} event(s) waiting over 45 minutes: is the "
                "15-minute Scheduler job running? (RUNBOOK §2.6)",
            )
        )
    if dead:
        checks.append(
            Check(
                "WARN",
                "background job",
                f"{dead} event(s) failed for good in the last 7 days "
                "(emails, revalidation): see the API log.",
            )
        )
    if not checks:
        checks.append(Check("PASS", "background job", "Nothing stuck; no failures this week."))
    return checks


def check_settings() -> list[Check]:
    settings = get_settings()
    checks: list[Check] = []
    env = settings.app_env
    if env != "production":
        checks.append(Check("WARN", "APP_ENV", f"{env}: run this again on production."))
    else:
        checks.append(Check("PASS", "APP_ENV", "production"))
    site_url = settings.site_url
    if not site_url.startswith("https://"):
        status: Status = "FAIL" if env == "production" else "WARN"
        checks.append(Check(status, "SITE_URL", f"{site_url} isn't https."))
    else:
        checks.append(Check("PASS", "SITE_URL", site_url))
    return checks


def run(db: Session) -> list[Check]:
    return [
        *check_settings(),
        *check_projects(db),
        *check_pages_and_posts(db),
        *check_site(db),
        *check_consent(db),
        *check_people(db),
        *check_features(db),
        *check_outbox(db),
    ]


def as_json(checks: list[Check]) -> list[dict[str, str]]:
    return [asdict(c) for c in checks]
