"""Dashboard shapes (design contract schemas Dashboard and DashboardCount).

Contract additions (Phase 4 part 3): tasks carry `key` and `detail` as well as `label` and
`link`; `leads_by_source` (last 30 days, counts only) feeds the board's "Leads by source" chart.
"""

from __future__ import annotations

from pydantic import Field

from empire_api.leads.schemas import Lead, SiteVisit
from empire_api.leads.vocab import LeadSource
from empire_api.projects.fields import OutModel


class DashboardCount(OutModel):
    key: str = Field(examples=["leads.new"])
    label: str
    count: int
    link: str = Field(description="CMS path with filters, e.g. /admin/leads?status=new")


class DashboardTask(OutModel):
    key: str = Field(examples=["project.rera_qr_missing"])
    label: str
    detail: str | None
    link: str = Field(description="CMS path where the task is done")


class SourceCount(OutModel):
    source: LeadSource
    count: int


class Dashboard(OutModel):
    counts: list[DashboardCount] = Field(description="Only the counts your role can open")
    latest_leads: list[Lead] = Field(description="Your newest 5 (all leads with leads.read_all)")
    upcoming_visits: list[SiteVisit]
    tasks: list[DashboardTask] = Field(
        description="E.g. projects missing the RERA QR, photos hidden until labelled, consent "
        "texts still awaiting the owner's approval"
    )
    leads_by_source: list[SourceCount] = Field(
        description="Last 30 days (IST), spam left out, counts only"
    )
