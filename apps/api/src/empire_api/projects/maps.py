"""Google Maps pin resolver: a pasted link, short link or plus code → latitude and longitude.

Collaborators: routes_catalogue.py (`POST /api/v1/admin/maps/resolve`), pluscode.py.
Implements: ARCHITECTURE §13 and D-012 (no Google API key; pins come from links and codes).

What it accepts:
  - Long Google Maps links. Coordinates are read from the URL, never fetched, in this order:
    the place pin `!3d<lat>!4d<lng>`; the query values `q=`, `query=`, `destination=`, `ll=`;
    a dropped pin in the path (`/maps/search/<lat>,<lng>` or `/maps/place/<lat>,<lng>`);
    then the map centre `@<lat>,<lng>`.
  - Short links (`maps.app.goo.gl/…`, `goo.gl/maps/…`), followed on the server.
  - Full plus codes (`7JWV8XX8+XX`, optionally followed by a place name). Short plus codes
    (`8XX8+XX Noida`) need a geocoder to place, so they get a 422 asking for the full code.

SECURITY: following short links makes this endpoint an SSRF surface (a staff session could try
to make the API fetch internal or arbitrary URLs). The defences, all in `follow_short_link`:
  1. Every hop, including the first, must be https, port 443, no user-info, to a host on the
     explicit allowlist below; www.google.* and goo.gl hosts must also be on a /maps path,
     which keeps Google's open redirect (/url?q=…) out. No wildcard hosts, ever.
  2. Redirects are followed one at a time by our own loop (the client's automatic redirects
     are off), so each Location is checked before it is used; at most 5 redirects.
  3. Only response headers are read. The body is never downloaded.
  4. One 5-second budget covers the whole resolution, enforced by a hard deadline on a worker
     thread (DNS lookups and slow servers can't hold the request longer).
  5. urllib and httpx must agree on scheme, host and port, so a URL the two parse differently
     (e.g. with a backslash) is refused.
  6. The route is staff-only (`projects.write`) and rate-limited per user.
Tests inject the HTTP client (`client_factory`) and never touch the network.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Final, Literal
from urllib.parse import SplitResult, parse_qs, unquote, urljoin, urlsplit

import httpx

from empire_api.logs import get_logger
from empire_api.projects import pluscode

MAX_REDIRECTS: Final = 5
TIMEOUT_SECONDS: Final = 5.0
MAX_URL_LENGTH: Final = 2048
REDIRECT_STATUSES: Final = frozenset({301, 302, 303, 307, 308})

# SECURITY: the only hosts a link may point to (rule 1 in the module header). Add a country
# domain explicitly if staff ever need one; never match by suffix or wildcard.
GOOGLE_MAPS_HOSTS: Final = frozenset(
    {
        "google.com",
        "www.google.com",
        "maps.google.com",
        "google.co.in",
        "www.google.co.in",
        "maps.google.co.in",
        "goo.gl",
        "maps.app.goo.gl",
    }
)
# Hosts that serve much more than maps: only their /maps paths are accepted.
_MAPS_PATH_ONLY_HOSTS: Final = frozenset(
    {"google.com", "www.google.com", "google.co.in", "www.google.co.in", "goo.gl"}
)
_USER_AGENT: Final = "EmpireCMS-MapsResolver/1.0"

NOT_A_LINK = (
    "Paste a Google Maps link (like https://maps.app.goo.gl/…) or a full plus code "
    "(like 7JWV8XX8+XX)."
)
TYPED_COORDINATES = (
    "To type a latitude and longitude, use the latitude and longitude fields. This box takes "
    "a Google Maps link or a plus code."
)
NOT_GOOGLE = (
    "Only Google Maps links work here (google.com/maps, maps.google.com, maps.app.goo.gl or "
    "goo.gl/maps)."
)
SHORT_PLUS_CODE = (
    "That is a short plus code, which needs a town to place it. Paste the full code "
    "(like 7JWV8XX8+XX) or a Google Maps link instead."
)
BAD_PLUS_CODE = "That isn't a valid plus code. Check it, or paste a Google Maps link instead."
ROUGH_PLUS_CODE = (
    "That plus code covers too large an area for a pin. Paste the full code with two or more "
    "characters after the +, or a Google Maps link."
)
NO_PIN = (
    "This link has no map pin in it. In Google Maps, open the place or drop a pin, choose "
    "Share, and paste that link."
)
LINK_BROKEN = "Google Maps didn't recognise that link. Check it and try again."
TOO_MANY_REDIRECTS = (
    "That link goes through too many redirects to follow safely. Open it in Google Maps and "
    "paste the full link from the address bar."
)
LEFT_GOOGLE = (
    "That link leads away from Google Maps, so it wasn't followed. Open it in Google Maps and "
    "paste the full link from the address bar."
)
TOO_SLOW = (
    "Google Maps took too long to answer. Try again, or paste the full link from the address bar."
)
UNREACHABLE = (
    "Google Maps couldn't be reached. Try again in a minute, or type the latitude and longitude."
)

PinKind = Literal["url_coordinates", "short_link", "plus_code"]
ClientFactory = Callable[[], httpx.Client]

log = get_logger(__name__)

_NUMBER = r"[-+]?\d{1,3}(?:\.\d+)?"
_PLACE_PIN = re.compile(rf"!3d({_NUMBER})!4d({_NUMBER})")
_MAP_CENTRE = re.compile(rf"@({_NUMBER}),({_NUMBER})(?=[,/?]|$)")
# A dropped pin shared from the app: /maps/search/28.535516,+77.391026 (also /maps/place/…).
# After decoding, "+" (literal or %2B) and spaces (literal or %20) may follow the comma.
_PATH_PIN = re.compile(rf"/maps/(?:search|place)/({_NUMBER})\s*,[\s+]*({_NUMBER})(?=[/?]|$)")
_PAIR = re.compile(rf"^(?:loc:)?\s*({_NUMBER})\s*,\s*({_NUMBER})$")
_PLUS_CODE = re.compile(r"^[23456789CFGHJMPQRVWX0]{2,8}\+[23456789CFGHJMPQRVWX]*$", re.IGNORECASE)
_QUERY_KEYS: Final = ("q", "query", "destination", "ll")

# One small pool for short-link lookups, so a hung lookup can't hold the request thread
# (SECURITY rule 4). Threads are created on first use.
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="maps-resolver")


class MapsInputError(ValueError):
    """Why the input gave no pin, written for staff. The route answers 422 with it."""


@dataclass(frozen=True)
class Pin:
    lat: float
    lng: float
    source: PinKind
    resolved_url: str | None
    # The full code alone, uppercase (place name dropped), when the pin came from a plus code.
    plus_code: str | None = None


def default_client() -> httpx.Client:
    """The production HTTP client: redirects off (we check each hop), small pool, our UA."""
    return httpx.Client(
        follow_redirects=False,
        timeout=httpx.Timeout(TIMEOUT_SECONDS),
        headers={"User-Agent": _USER_AGENT, "Accept": "text/html"},
        limits=httpx.Limits(max_connections=2, max_keepalive_connections=0),
    )


def resolve(
    text: str,
    *,
    client_factory: ClientFactory | None = None,
    timeout_seconds: float = TIMEOUT_SECONDS,
) -> Pin:
    """Turn pasted text into a pin. Raises `MapsInputError` with a staff-facing reason.

    How it works:
      1. A plus code (first word contains "+") is decoded locally.
      2. Otherwise the text must be a Google Maps URL on the allowlist.
      3. A short link is followed on the server (SECURITY rules in the module header).
      4. A long link is read for coordinates without any network call.
    """
    text = text.strip()
    if not text or len(text) > MAX_URL_LENGTH:
        raise MapsInputError(NOT_A_LINK)
    plus = _plus_code_pin(text)  # 1
    if plus is not None:
        return plus
    if _PAIR.match(text):
        raise MapsInputError(TYPED_COORDINATES)
    parts = _google_maps_url(text)  # 2
    if is_short_link(parts):  # 3
        https_url = parts._replace(scheme="https").geturl()
        factory = client_factory or default_client  # looked up now, so tests can replace it
        lat, lng, final_url = _follow_with_deadline(https_url, factory, timeout_seconds)
        return Pin(lat, lng, "short_link", final_url)
    coordinates = coordinates_from_url(parts.geturl())  # 4
    if coordinates is None:
        raise MapsInputError(NO_PIN)
    return Pin(coordinates[0], coordinates[1], "url_coordinates", parts.geturl())


# --- Pure parsing ----------------------------------------------------------------------------


def _plus_code_pin(text: str) -> Pin | None:
    """A pin from a full plus code, None when the text is not a plus code at all."""
    token = pluscode.leading_code(text)
    if not _PLUS_CODE.match(token):
        return None
    if pluscode.is_short(token):
        raise MapsInputError(SHORT_PLUS_CODE)
    if not pluscode.is_full(token):
        raise MapsInputError(BAD_PLUS_CODE)
    if len(token) - token.index("+") - 1 < 2:
        raise MapsInputError(ROUGH_PLUS_CODE)
    area = pluscode.decode(token)
    return Pin(round(area.lat, 6), round(area.lng, 6), "plus_code", None, plus_code=token.upper())


def _google_maps_url(text: str) -> SplitResult:
    """Parse `text` as a URL (https:// added when missing) and check it is a Google Maps link."""
    candidate = text if "://" in text else f"https://{text}"
    if any((ch.isspace() and ch != " ") or ch == "\\" for ch in candidate):
        raise MapsInputError(NOT_A_LINK)
    # WHY: a link copied by hand may keep a space ("…/search/28.53, 77.39"); encode it as a
    # browser would, so every later step sees one well-formed URL.
    parts = urlsplit(candidate.replace(" ", "%20"))
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise MapsInputError(NOT_A_LINK)
    if not is_google_maps_url(parts):
        raise MapsInputError(NOT_GOOGLE)
    return parts


def is_google_maps_url(parts: SplitResult, *, https_only: bool = False) -> bool:
    """True for an allowlisted Google Maps host (and /maps path where needed), no user-info,
    default port. `https_only` is the stricter rule for hops we fetch (SECURITY rule 1)."""
    try:
        port = parts.port
    except ValueError:
        return False
    schemes, ports = (
        (("https",), (None, 443)) if https_only else (("http", "https"), (None, 80, 443))
    )
    host = (parts.hostname or "").rstrip(".")
    if (
        parts.username is not None
        or parts.password is not None
        or parts.scheme not in schemes
        or port not in ports
        or host not in GOOGLE_MAPS_HOSTS
    ):
        return False
    if host in _MAPS_PATH_ONLY_HOSTS:
        return parts.path == "/maps" or parts.path.startswith("/maps/")
    return True


def is_short_link(parts: SplitResult) -> bool:
    host = (parts.hostname or "").rstrip(".")
    return host == "maps.app.goo.gl" or (host == "goo.gl" and parts.path.startswith("/maps"))


def coordinates_from_url(url: str) -> tuple[float, float] | None:
    """Read (lat, lng) from a Google Maps URL, or None. No network (order in module header)."""
    parts = urlsplit(url)
    pins = _PLACE_PIN.findall(unquote(url))
    if pins:
        found = _valid(*pins[-1])  # the last pin in a place URL is the place itself
        if found:
            return found
    query = parse_qs(parts.query)
    for key in _QUERY_KEYS:
        for value in query.get(key, []):
            match = _PAIR.match(value.strip())
            found = _valid(*match.groups()) if match else None
            if found:
                return found
    path = unquote(parts.path)
    for pattern in (_PATH_PIN, _MAP_CENTRE):
        match = pattern.search(path)
        found = _valid(*match.groups()) if match else None
        if found:
            return found
    return None


def _valid(lat_text: str, lng_text: str) -> tuple[float, float] | None:
    lat, lng = float(lat_text), float(lng_text)
    if -90 <= lat <= 90 and -180 <= lng <= 180:
        # Six decimals (about 11 cm) is what the project row stores.
        return round(lat, 6), round(lng, 6)
    return None


# --- Network (short links only) --------------------------------------------------------------


def _follow_with_deadline(
    url: str, client_factory: ClientFactory, timeout_seconds: float
) -> tuple[float, float, str]:
    """Run `follow_short_link` on a worker thread and give up after `timeout_seconds` in total.

    WHY a thread: httpx timeouts apply per network step and don't cover DNS lookups, so only a
    hard deadline guarantees the 5-second budget. A thread still running after the deadline ends
    on its own per-step timeouts; its result is discarded.
    """
    deadline = time.monotonic() + timeout_seconds

    def work() -> tuple[float, float, str]:
        with client_factory() as client:
            return follow_short_link(url, client, deadline=deadline)

    future = _EXECUTOR.submit(work)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeout as exc:
        future.cancel()
        log.warning("maps_resolve_timeout", host=urlsplit(url).hostname)
        raise MapsInputError(TOO_SLOW) from exc


def follow_short_link(
    url: str, client: httpx.Client, *, deadline: float, max_redirects: int = MAX_REDIRECTS
) -> tuple[float, float, str]:
    """Follow a short link hop by hop until a URL carries coordinates. Returns (lat, lng, url).

    How it works:
      1. Check the hop (SECURITY rules 1 and 5), then request it reading headers only (rule 3).
      2. A redirect's Location is resolved against the current URL and checked BEFORE anything
         else is done with it; if it already carries coordinates we stop without fetching it.
      3. More than `max_redirects` redirects, an error status or a final page without
         coordinates → `MapsInputError`.
    """
    current, redirects = url, 0
    while True:
        _check_hop(current)  # 1
        status, location = _fetch_headers(client, current, deadline)
        if status not in REDIRECT_STATUSES:
            raise MapsInputError(LINK_BROKEN if status >= 400 else NO_PIN)  # 3
        redirects += 1
        if redirects > max_redirects:
            raise MapsInputError(TOO_MANY_REDIRECTS)
        if not location or len(location) > MAX_URL_LENGTH:
            raise MapsInputError(LINK_BROKEN)
        current = urljoin(current, location)  # 2
        _check_hop(current)
        coordinates = coordinates_from_url(current)
        if coordinates is not None:
            return coordinates[0], coordinates[1], current


def _check_hop(url: str) -> None:
    """SECURITY rules 1 and 5: https to an allowlisted Google Maps host, parsed identically."""
    parts = urlsplit(url)
    if any(ch.isspace() or ch == "\\" for ch in url) or not is_google_maps_url(
        parts, https_only=True
    ):
        log.warning("maps_resolve_refused_hop", host=parts.hostname)
        raise MapsInputError(LEFT_GOOGLE)
    try:
        theirs = httpx.URL(url)
    except httpx.InvalidURL as exc:
        raise MapsInputError(LEFT_GOOGLE) from exc
    if (theirs.scheme, theirs.host, theirs.port or 443) != (
        "https",
        parts.hostname,
        parts.port or 443,
    ):
        log.warning("maps_resolve_parser_mismatch", host=parts.hostname)
        raise MapsInputError(LEFT_GOOGLE)


def _fetch_headers(client: httpx.Client, url: str, deadline: float) -> tuple[int, str | None]:
    """One GET, headers only; the budget left is the timeout for every network step."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise MapsInputError(TOO_SLOW)
    try:
        with client.stream("GET", url, follow_redirects=False, timeout=remaining) as response:
            # SECURITY rule 3: the body is never read; leaving the block closes the connection.
            return response.status_code, response.headers.get("location")
    except httpx.TimeoutException as exc:
        log.warning("maps_resolve_timeout", host=urlsplit(url).hostname)
        raise MapsInputError(TOO_SLOW) from exc
    except httpx.HTTPError as exc:
        log.warning("maps_resolve_unreachable", error_type=type(exc).__name__)
        raise MapsInputError(UNREACHABLE) from exc
