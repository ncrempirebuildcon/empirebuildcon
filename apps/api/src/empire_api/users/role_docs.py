"""Plain-English wording for the role table in the CMS (users and roles board): a sentence per
role and the group each permission is listed under.

Collaborators: users/routes_admin.py (GET /admin/roles, GET /admin/permissions).
WHY a separate file from roles.py: this is wording only. It can change in a normal review,
while roles.py (who may do what) needs owner approval. A test checks that every permission in
roles.py has a group here, so the table can't silently drop a row.
"""

from __future__ import annotations

from typing import Final

ROLE_SUMMARIES: Final[dict[str, str]] = {
    "super_admin": "Everything, including users and roles and erasing a buyer's personal data on "
    "request. One account at launch: the owner.",
    "admin": "Runs the CMS day to day: projects, leads, content, offers, settings, flags and the "
    "audit log. Can't manage users or erase data.",
    "sales": "Works their own leads and the site-visit calendar. Sees projects read-only and the "
    "UTM report as counts only.",
    "marketing": "Offers, tracking IDs, SEO, pages, posts and media. Sees lead counts by source, "
    "never lead details.",
    "content_editor": "Projects, configurations, pages, posts, FAQs, media and SEO. Can't publish "
    "projects or see leads.",
}

_GROUPS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    (
        "Dashboard & projects",
        (
            "dashboard.view",
            "projects.read",
            "projects.write",
            "projects.publish",
            "projects.delete",
        ),
    ),
    ("Media", ("media.upload", "media.manage")),
    (
        "Leads & site visits",
        (
            "leads.read",
            "leads.read_all",
            "leads.update",
            "leads.assign",
            "leads.export",
            "leads.report",
            "leads.erase",
            "site_visits.manage",
        ),
    ),
    (
        "Content & SEO",
        (
            "content.read",
            "content.write",
            "content.publish",
            "legal.publish",
            "offers.manage",
            "seo.manage",
        ),
    ),
    (
        "Settings & system",
        (
            "settings.read",
            "settings.write",
            "marketing.tracking",
            "flags.manage",
            "integrations.manage",
            "audit.read",
            "users.manage",
        ),
    ),
)
PERMISSION_GROUPS: Final[dict[str, str]] = {
    permission: group for group, permissions in _GROUPS for permission in permissions
}
