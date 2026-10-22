"""Roles and the permission matrix: the single source of truth for who may do what.

Implements: ARCHITECTURE §11 exactly. The CMS reads it through `GET /api/v1/admin/roles`;
the API enforces it through `require()` in users/deps.py.

DO NOT CHANGE without owner approval (CONTRIBUTING §7): adding a permission to a role widens
what that role can see or change. Update ARCHITECTURE §11 and the users-and-roles board in the
same pull request, and add a test for the new rule.
"""

from __future__ import annotations

from typing import Final, Literal

RoleKey = Literal["super_admin", "admin", "sales", "marketing", "content_editor"]

ROLE_NAMES: Final[dict[str, str]] = {
    "super_admin": "Super-admin",
    "admin": "Admin",
    "sales": "Sales",
    "marketing": "Marketing",
    "content_editor": "Content editor",
}
ROLE_KEYS: Final[tuple[str, ...]] = tuple(ROLE_NAMES)

_ALL = frozenset(ROLE_KEYS)
_SA = frozenset({"super_admin"})
_SA_A = frozenset({"super_admin", "admin"})

# permission → (what it allows, roles that have it). Order follows ARCHITECTURE §11.
PERMISSIONS: Final[dict[str, tuple[str, frozenset[str]]]] = {
    "dashboard.view": ("Dashboard", _ALL),
    "projects.read": ("See projects in the CMS", _ALL),
    "projects.write": (
        "Edit projects, towers, configurations, cities, amenities",
        _SA_A | {"content_editor"},
    ),
    "projects.publish": ("Publish / unpublish projects", _SA_A),
    "projects.delete": ("Delete draft projects", _SA_A),
    "media.upload": (
        "Upload, attach, order, cover, show/hide",
        _SA_A | {"marketing", "content_editor"},
    ),
    "media.manage": ("Delete from the library", _SA_A | {"content_editor"}),
    "leads.read": ("Open leads assigned to them", _SA_A | {"sales"}),
    "leads.read_all": ("See every lead", _SA_A),
    "leads.update": ("Status, notes, details, manual leads", _SA_A | {"sales"}),
    "leads.assign": ("Change a lead's owner", _SA_A),
    "leads.export": ("CSV export (audited)", _SA_A),
    "leads.report": ("UTM report (counts only, no personal data)", _SA_A | {"sales", "marketing"}),
    "leads.erase": ("Erase personal data on request", _SA),
    "site_visits.manage": ("Visit calendar", _SA_A | {"sales"}),
    "content.read": (
        "Pages, blocks, posts, FAQs, testimonials (read)",
        _SA_A | {"marketing", "content_editor"},
    ),
    "content.write": (
        "Pages, blocks, posts, FAQs, testimonials (edit)",
        _SA_A | {"marketing", "content_editor"},
    ),
    "content.publish": (
        "Publish pages, posts, FAQs, testimonials",
        _SA_A | {"marketing", "content_editor"},
    ),
    "legal.publish": ("Legal pages and consent texts", _SA_A),
    "offers.manage": ("Offers and banners", _SA_A | {"marketing"}),
    "seo.manage": ("SEO fields, redirects", _SA_A | {"marketing", "content_editor"}),
    "settings.read": ("See settings", _SA_A | {"marketing"}),
    "settings.write": ("Company, contacts, lead routing", _SA_A),
    "marketing.tracking": ("GTM, GA4, Pixel, Ads IDs", _SA_A | {"marketing"}),
    "flags.manage": ("Feature flags", _SA_A),
    "integrations.manage": ("Webhooks, CRM, alerts", _SA_A),
    "audit.read": ("Audit log", _SA_A),
    "users.manage": ("Accounts and roles", _SA),
}


def permissions_for(role: str) -> list[str]:
    """Sorted permission keys for a role (empty for an unknown role: fail closed)."""
    return sorted(p for p, (_, roles) in PERMISSIONS.items() if role in roles)


def has_permission(role: str, permission: str) -> bool:
    entry = PERMISSIONS.get(permission)
    return entry is not None and role in entry[1]
