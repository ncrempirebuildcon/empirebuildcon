"""The fixed lists of the SEO module: redirect status codes and origins, our own domains, and
the paths a redirect may never start from.

DO NOT CHANGE a stored value without a migration: the CHECK constraints in
migrations/versions/0005_content.py list them.
"""

from __future__ import annotations

from typing import Final, Literal, get_args

RedirectStatus = Literal["301", "308"]
REDIRECT_STATUS_CODES: Final = (301, 308)
# `manual`: typed in the CMS. The others: made automatically when a published page, post or
# project changed its slug (seo/redirects.py slug_changed).
RedirectOrigin = Literal["manual", "page", "post", "project"]
REDIRECT_ORIGINS: Final = get_args(RedirectOrigin)

# D-008: the apex is canonical; the other names answer 308 to the same path on it. A redirect
# target on any of them is stored as the path alone.
OUR_HOSTS: Final = frozenset(
    {
        "empirebuildcon.com",
        "www.empirebuildcon.com",
        "empirebuildcon.in",
        "www.empirebuildcon.in",
        "empirebuildcon.co.in",
        "www.empirebuildcon.co.in",
    }
)
# SECURITY: the CMS, the API and Next.js internals are never redirected (a redirect there could
# lock staff out of /admin or break the site's own assets). "/" is the home page.
RESERVED_PREFIXES: Final = ("/admin", "/api", "/_next", "/_internal")
MAX_PATH: Final = 500
