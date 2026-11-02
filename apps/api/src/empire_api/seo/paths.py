"""Public paths: where a page, post or project lives on the website, and the rules for the two
ends of a redirect.

Collaborators: redirects.py, seo/schemas.py (validators), content/pages.py and posts.py
(`path` in responses, redirects on slug changes), projects/service.py.
Implements: ARCHITECTURE §16 (clean slugs, redirects manager), SECURITY.md §5 ("`to_path` must
be a site path or an allow-listed host; no open redirects"), D-008 (our domains).

Paths (Phase 5 builds the pages at exactly these addresses):
  - page: `/<slug>`; the home page (system page `home`) is `/`.
  - post: `/blog/<slug>`.
  - project: `/projects/<slug>`.

Phase 5 contract (review L6): paths are matched exactly, case-sensitively, after dropping one
trailing slash. `/About` and `/about` are different addresses, so the redirect middleware must
not fold case, and loops and chains are judged on exact paths. Only the reserved-path check
ignores case, because a case-insensitive server or proxy could still route `/Admin` to the CMS.
"""

from __future__ import annotations

from typing import Final
from urllib.parse import urlsplit

from pydantic_core import PydanticCustomError

from empire_api.projects.fields import is_site_path
from empire_api.seo.vocab import MAX_PATH, OUR_HOSTS, RESERVED_PREFIXES

HOME_SLUG: Final = "home"
# Slugs a page (other than the system page of the same name) can't take: they are the
# website's own sections, or the CMS and API.
RESERVED_PAGE_SLUGS: Final = frozenset(
    {
        "admin",
        "api",
        "blog",
        "cities",
        "home",
        "hi",
        "en",
        "projects",
        "properties",
        "search",
        "sitemap",
    }
)
FROM_MESSAGE: Final = (
    "Enter the old address as a path starting with /, like /old-page, without ? or #."
)
TO_MESSAGE: Final = (
    "Redirects can only go to a page on our website: a path starting with /, or a full "
    "https://empirebuildcon.com address."
)
RESERVED_MESSAGE: Final = "Addresses under /admin, /api and the site's own files can't redirect."


def page_path(slug: str) -> str:
    return "/" if slug == HOME_SLUG else f"/{slug}"


def post_path(slug: str) -> str:
    return f"/blog/{slug}"


def project_path(slug: str) -> str:
    return f"/projects/{slug}"


def property_path(project_slug: str, config_slug: str) -> str:
    """One configuration's page (D-041). The web twin is apps/web/src/lib/public/catalogue.ts."""
    return f"/projects/{project_slug}/{config_slug}"


def city_path(slug: str) -> str:
    """A city's projects (D-041); "cities" is a reserved page slug so no page can take it."""
    return f"/cities/{slug}"


def _clean(value: str) -> bool:
    return not any(ch.isspace() or ord(ch) < 32 or ch == "\\" for ch in value)


def _is_reserved(path: str) -> bool:
    """SECURITY: /admin, /api and the site's own files, in any case (module header, L6)."""
    folded = path.lower()
    return any(folded == prefix or folded.startswith(prefix + "/") for prefix in RESERVED_PREFIXES)


def _trim(path: str) -> str:
    """`/a/` → `/a` (the API and the site treat both the same, ARCHITECTURE §3); `/` stays."""
    trimmed = path.rstrip("/")
    return trimmed or "/"


def owner_of_path(path: str) -> tuple[str, str] | None:
    """Which kind of thing the website shows at `path`, and its slug: ("page", slug),
    ("post", slug) or ("project", slug); None for any other address (module header)."""
    segments = path.strip("/").split("/")
    if len(segments) == 1 and segments[0] and segments[0] != HOME_SLUG:  # home lives at /
        return "page", segments[0]
    if len(segments) == 2 and segments[0] in ("blog", "projects") and segments[1]:
        return ("post" if segments[0] == "blog" else "project"), segments[1]
    return None


def path_of(target: str) -> str:
    """The path part of a stored target: `/a?x=1#y` → `/a`."""
    return urlsplit(target).path or "/"


def normalise_from_path(value: str) -> str:
    """The old address a redirect answers for: a site path without query or fragment."""
    value = value.strip()
    if (
        not value.startswith("/")
        or value.startswith("//")
        or "?" in value
        or "#" in value
        or not _clean(value)
        or len(value) > MAX_PATH
    ):
        raise PydanticCustomError("from_path", FROM_MESSAGE)
    path = _trim(value)
    if path == "/":
        raise PydanticCustomError("from_path", "The home page can't be redirected.")
    if _is_reserved(path):
        raise PydanticCustomError("from_path", RESERVED_MESSAGE)
    return path


def normalise_target(value: str) -> str:
    """Where a redirect goes: a site path (query and fragment allowed), or an https address on
    one of our domains, stored as its path.

    SECURITY (SECURITY.md §5, review H1): no other host, so no open redirect. The stored value
    is the `Location` the website sends, so it must itself be a site path: the address
    `https://empirebuildcon.com//evil.example` has the path `//evil.example`, which a browser
    reads as another host. The final value is checked again with `is_site_path`, and the
    database CHECK `ck_redirect_to_path_is_site_path` backs it up.
    """
    value = value.strip()
    if not _clean(value) or len(value) > MAX_PATH:
        raise PydanticCustomError("to_path", TO_MESSAGE)
    parts = urlsplit(value)
    if not is_site_path(value):
        host_ok = parts.scheme == "https" and (parts.hostname or "").lower() in OUR_HOSTS
        if not host_ok or parts.username or parts.password or parts.port:
            raise PydanticCustomError("to_path", TO_MESSAGE)
    path = _trim(parts.path or "/")
    if _is_reserved(path):
        raise PydanticCustomError("to_path", RESERVED_MESSAGE)
    query = f"?{parts.query}" if parts.query else ""
    fragment = f"#{parts.fragment}" if parts.fragment else ""
    target = f"{path}{query}{fragment}"
    if not is_site_path(target) or len(target) > MAX_PATH:
        raise PydanticCustomError("to_path", TO_MESSAGE)
    return target


def split_target(target: str) -> tuple[str, str, str]:
    """A stored target → (path, "?query" or "", "#fragment" or "")."""
    parts = urlsplit(target)
    query = f"?{parts.query}" if parts.query else ""
    fragment = f"#{parts.fragment}" if parts.fragment else ""
    return parts.path or "/", query, fragment
