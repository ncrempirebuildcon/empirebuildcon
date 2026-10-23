"""Read CLOUDINARY_URL (`cloudinary://<api_key>:<api_secret>@<cloud_name>`) into its parts.

Collaborators: config.py (refuses a malformed value at start-up), cloudinary_store.py.

SECURITY: errors name the problem, never the value, so they are safe to log (SECURITY.md §7).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

# Cloudinary cloud names: lowercase letters, digits, hyphens and underscores.
_CLOUD_NAME = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


@dataclass(frozen=True)
class CloudinaryCredentials:
    cloud_name: str
    api_key: str
    # SECURITY: kept out of repr so a logged object never shows it.
    api_secret: str = field(repr=False)


def parse_cloudinary_url(value: str) -> CloudinaryCredentials:
    """Split the URL. Raises ValueError with a value-free message when it is malformed."""
    parts = urlsplit(value.strip())
    if parts.scheme != "cloudinary":
        raise ValueError("CLOUDINARY_URL must start with cloudinary://")
    # WHY not parts.hostname: it lower-cases, and the credentials may hold characters that
    # urlsplit's host parsing rejects; split the authority by hand instead.
    userinfo, _, cloud_name = parts.netloc.rpartition("@")
    api_key, _, api_secret = userinfo.partition(":")
    if not (api_key and api_secret and _CLOUD_NAME.match(cloud_name)):
        raise ValueError(
            "CLOUDINARY_URL must look like cloudinary://<api_key>:<api_secret>@<cloud_name>"
        )
    return CloudinaryCredentials(
        cloud_name=cloud_name, api_key=unquote(api_key), api_secret=unquote(api_secret)
    )
