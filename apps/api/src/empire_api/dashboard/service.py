"""The dashboard: counts that link to filtered lists, the latest leads, upcoming visits and tasks
(ARCHITECTURE §8 "dashboard counts link to the filtered inbox").

Collaborators: leads/queries.py, projects/queries.py, media/queries.py, content/consent.py;
dashboard/routes.py (HTTP).
Implements: ARCHITECTURE §8, §11 (each part is shown only to roles that can open it), D-015
(warn while sample data exists), D-017 (consent wording awaiting approval), D-002 (RERA QR).

SECURITY (SECURITY.md §1): lead counts, latest leads and visits go through the leads module's
object-level rule, so sales see their own only. A role without `leads.read` gets no lead
counts or latest leads, and one without `site_visits.manage` no visits: their links would
only answer 403.
Every `link` is a CMS path whose query string the CMS list understands, and INVARIANT: the
list it opens shows exactly `count` items, because both come from the same filters
(/admin/leads?owner_id=unassigned&open=true, /admin/site-visits?from=…&to=…&open=true,
/admin/projects?publish_state=draft&blocked=true, …). `leads_by_source` uses the UTM report's
counts-only scope, so marketing sees it too.
"""

from __future__ import annotations

from typing import Final
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from empire_api.content import consent
from empire_api.dashboard.schemas import Dashboard, DashboardCount, DashboardTask, SourceCount
from empire_api.leads import present
from empire_api.leads import queries as lead_queries
from empire_api.leads.access import Staff
from empire_api.leads.filters import LeadFilters
from empire_api.leads.visits import VisitFilters
from empire_api.media import queries as media_queries
from empire_api.projects import queries as project_queries
from empire_api.projects.blockers import RERA_QR_MISSING
from empire_api.timeutil import today_ist

LATEST: Final = 5
UPCOMING: Final = 5
SOURCE_DAYS: Final = 30
MAX_TASKS: Final = 20
CONSENT_LINK: Final = "/admin/settings?tab=consent"


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def _link(path: str, **query: str) -> str:
    return f"{path}?{urlencode(query)}" if query else path


# (key, label, filters). INVARIANT: each count and its link come from the same filters, so the
# number on the tile is the total the linked list shows (tests/test_leads_review_rules.py).
_LEAD_COUNTS: Final = (
    ("leads.new", "New leads", LeadFilters(status="new")),
    ("leads.unread", "Unread leads", LeadFilters(read=False)),
    ("leads.unassigned", "Unassigned leads", LeadFilters(owner_id="unassigned", open=True)),
)


def _lead_counts(db: Session, staff: Staff) -> list[DashboardCount]:
    found = []
    for key, label, filters in _LEAD_COUNTS:
        if key == "leads.unassigned" and not staff.sees_all_leads:
            continue  # sales never see unassigned leads, so the tile would always say 0
        found.append(
            DashboardCount(
                key=key,
                label=label,
                count=lead_queries.count_matching(db, staff, filters),
                link=_link("/admin/leads", **filters.query_params()),
            )
        )
    return found


def _visit_counts(db: Session, staff: Staff) -> list[DashboardCount]:
    today = today_ist()
    monday, sunday = lead_queries.week_bounds(today)
    found = []
    for key, label, first, last in (
        ("visits.today", "Site visits today", today, today),
        ("visits.week", "Site visits this week", monday, sunday),
    ):
        filters = VisitFilters(date_from=first, date_to=last, open=True)
        found.append(
            DashboardCount(
                key=key,
                label=label,
                count=lead_queries.count_visits(db, staff, filters),
                link=_link("/admin/site-visits", **filters.query_params()),
            )
        )
    return found


def _project_counts(db: Session, blocked: int) -> list[DashboardCount]:
    states = project_queries.publish_state_counts(db)
    return [
        DashboardCount(
            key="projects.published",
            label="Projects published",
            count=states["published"],
            link=_link("/admin/projects", publish_state="published"),
        ),
        DashboardCount(
            key="projects.draft",
            label="Drafts",
            count=states["draft"],
            link=_link("/admin/projects", publish_state="draft"),
        ),
        DashboardCount(
            key="projects.blocked",
            label="Drafts blocked from publishing",
            count=blocked,
            link=_link("/admin/projects", publish_state="draft", blocked="true"),
        ),
    ]


def _consent_tasks(db: Session) -> list[DashboardTask]:
    """COMPLIANCE (D-017): wording awaiting the owner's approval, or no wording at all."""
    tasks: list[DashboardTask] = []
    lead_form = consent.current_text(db, "lead_form")
    if lead_form is None:
        tasks.append(
            DashboardTask(
                key="consent.lead_form_missing",
                label="Enquiries are closed",
                detail="No enquiry consent text is published, so the website's forms can't "
                "take enquiries. Publish the owner-approved wording.",
                link=CONSENT_LINK,
            )
        )
    for kind, label in (("lead_form", "enquiry"), ("marketing", "marketing")):
        text = lead_form if kind == "lead_form" else consent.current_text(db, kind)
        if text is not None and consent.is_draft(text):
            tasks.append(
                DashboardTask(
                    key=f"consent.{kind}_draft",
                    label=f"The {label} consent text is still a draft",
                    detail=f"Version {text.version} is waiting for the owner's approval (D-017). "
                    "Publish a version without the draft mark once it is approved.",
                    link=CONSENT_LINK,
                )
            )
    return tasks


def _project_tasks(
    db: Session, blocked: list[project_queries.BlockedProject], staff: Staff
) -> list[DashboardTask]:
    tasks: list[DashboardTask] = []
    if staff.can("media.upload"):
        for item in blocked:
            if any(b.message == RERA_QR_MISSING for b in item.blockers):
                tasks.append(
                    DashboardTask(
                        key="project.rera_qr_missing",
                        label=f"Publish blocked: {item.ref.name}",
                        detail="The UP-RERA QR code is missing. Upload it to publish the project.",
                        link=_link(f"/admin/projects/{item.ref.id}", tab="media"),
                    )
                )
        hidden = media_queries.hidden_unlabelled_photos(db)
        for project_id, ref in project_queries.project_refs(db, hidden).items():
            tasks.append(
                DashboardTask(
                    key="project.photos_unlabelled",
                    label=f"{ref.name}: "
                    + _plural(hidden[project_id], "photo", "photos")
                    + " hidden until labelled",
                    detail="Label each as an artist's impression, actual photo or progress "
                    "photo to show it on the website.",
                    link=_link(f"/admin/projects/{project_id}", tab="media"),
                )
            )
    samples = project_queries.sample_project_count(db)
    if samples:
        tasks.append(
            DashboardTask(
                key="projects.sample_data",
                label=_plural(samples, "sample project is", "sample projects are")
                + " still in the system",
                detail="They never show on the live site. Delete them once the real projects "
                "are added.",
                link="/admin/projects",
            )
        )
    return tasks


def dashboard(db: Session, staff: Staff) -> Dashboard:
    """Everything the CMS home shows, for this staff member's role (module header)."""
    counts: list[DashboardCount] = []
    tasks: list[DashboardTask] = []
    reads_leads = staff.can("leads.read")
    if reads_leads:
        counts += _lead_counts(db, staff)
    if staff.can("site_visits.manage"):
        counts += _visit_counts(db, staff)
    if staff.can("projects.read"):
        blocked = project_queries.blocked_drafts(db)
        counts += _project_counts(db, len(blocked))
        tasks += _project_tasks(db, blocked, staff)
    if staff.can("legal.publish"):
        tasks = _consent_tasks(db) + tasks
    today = today_ist()
    latest = lead_queries.latest_leads(db, staff, LATEST) if reads_leads else []
    upcoming = (
        lead_queries.upcoming_visits(db, staff, today, UPCOMING)
        if staff.can("site_visits.manage")
        else []
    )
    # Counts only: the UTM report's scope, so marketing (leads.report) sees them too.
    sources = (
        lead_queries.leads_by_source(db, staff, lead_queries.days_back(today, SOURCE_DAYS))
        if reads_leads or staff.can("leads.report")
        else []
    )
    return Dashboard(
        counts=counts,
        latest_leads=present.leads_out(db, latest, staff),
        upcoming_visits=present.visits_out(db, upcoming),
        tasks=tasks[:MAX_TASKS],
        leads_by_source=[SourceCount(source=s, count=n) for s, n in sources],
    )
