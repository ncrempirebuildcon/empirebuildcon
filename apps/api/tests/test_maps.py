"""Google Maps pin resolver (projects/maps.py), plus codes (projects/pluscode.py) and the
`POST /api/v1/admin/maps/resolve` endpoint.

SECURITY: the short-link tests use a fake HTTP client (httpx.MockTransport) and check the SSRF
rules: allowlisted https hosts only, hop by hop, at most 5 redirects, headers only, 5 s budget.
No test reaches the network (conftest.no_network fails any that tries).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator

import httpx
import pytest
from fastapi import FastAPI

from conftest import SignedIn, make_user, new_client, sign_in
from empire_api.projects import maps, pluscode, routes_catalogue
from empire_api.projects.maps import MapsInputError, coordinates_from_url, resolve

# Taken at import, before conftest.no_network replaces it for every test.
REAL_DEFAULT_CLIENT = maps.default_client

# --- Coordinates in long links (no network) --------------------------------------------------

PLACE = (
    "https://www.google.com/maps/place/Taj+Mahal/@27.1751448,78.0399535,17z/data=!3m1!4b1"
    "!4m6!3m5!1s0x39747121d702ff6d:0xdd2ae4803f767dde!8m2!3d27.1751448!4d78.0421422!16zL20v"
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (PLACE, (27.175145, 78.042142)),  # the place pin wins over the map centre (@)
        ("https://www.google.com/maps/@28.6129,77.2295,15z", (28.6129, 77.2295)),
        ("https://www.google.com/maps/@-33.8688,151.2093,12z", (-33.8688, 151.2093)),
        ("https://www.google.com/maps/@28.61,77.22,3a,75y,90t/data=!3m6", (28.61, 77.22)),
        ("https://maps.google.com/?q=28.6129,77.2295", (28.6129, 77.2295)),
        ("https://maps.google.com/maps?q=loc:28.6129,77.2295", (28.6129, 77.2295)),
        ("https://www.google.com/maps?q=28.6129,+77.2295&z=15", (28.6129, 77.2295)),
        ("https://www.google.com/maps/search/?api=1&query=28.6129%2C77.2295", (28.6129, 77.2295)),
        ("https://www.google.com/maps/dir/?api=1&destination=28.6129,77.2295", (28.6129, 77.2295)),
        ("https://maps.google.co.in/maps?ll=28.6129,77.2295&z=15", (28.6129, 77.2295)),
        ("https://maps.google.com/?q=28.1,77.1&ll=28.9,77.9", (28.1, 77.1)),  # q before ll
        ("https://www.google.com/maps/@28.61291234,77.22951234,15z", (28.612912, 77.229512)),
        # Dropped pins shared from the app: coordinates in the /search/ or /place/ segment.
        (
            "https://www.google.com/maps/search/28.535516,+77.391026?entry=tts",
            (28.535516, 77.391026),
        ),
        ("https://www.google.com/maps/search/28.535516,%2B77.391026", (28.535516, 77.391026)),
        ("https://www.google.com/maps/search/28.535516,%2077.391026/", (28.535516, 77.391026)),
        ("https://www.google.com/maps/search/28.535516, 77.391026", (28.535516, 77.391026)),
        ("https://www.google.com/maps/search/28.535516%2C77.391026", (28.535516, 77.391026)),
        (
            "https://www.google.com/maps/place/28.535516,77.391026/@28.53,77.39,17z",
            (28.535516, 77.391026),
        ),
        ("https://www.google.com/maps/place/-33.8688,+151.2093", (-33.8688, 151.2093)),
    ],
)
def test_coordinates_from_long_links(url: str, expected: tuple[float, float]) -> None:
    assert coordinates_from_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://www.google.com/maps?q=Taj+Mahal",
        "https://www.google.com/maps/place/Taj+Mahal/",
        "https://www.google.com/maps/@95.0,77.0,15z",  # latitude out of range
        "https://maps.google.com/?q=28.6,190.2",  # longitude out of range
    ],
)
def test_links_without_a_usable_pin(url: str) -> None:
    assert coordinates_from_url(url) is None


def test_resolve_long_link_without_network() -> None:
    pin = resolve("https://www.google.com/maps/@28.6129,77.2295,15z")
    assert (pin.lat, pin.lng, pin.source) == (28.6129, 77.2295, "url_coordinates")
    assert pin.resolved_url == "https://www.google.com/maps/@28.6129,77.2295,15z"


def test_resolve_adds_the_scheme() -> None:
    pin = resolve("www.google.com/maps/@28.6129,77.2295,15z")
    assert (pin.lat, pin.lng) == (28.6129, 77.2295)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("https://example.com/maps/@28.6,77.2,15z", maps.NOT_GOOGLE),
        ("https://maps.google.com.evil.example/?q=28.6,77.2", maps.NOT_GOOGLE),
        ("https://maps.google.com@evil.example/?q=28.6,77.2", maps.NOT_GOOGLE),
        ("https://www.google.com/url?q=https://evil.example", maps.NOT_GOOGLE),
        ("https://www.google.com/search?q=28.6,77.2", maps.NOT_GOOGLE),
        ("https://maps.google.com:8443/?q=28.6,77.2", maps.NOT_GOOGLE),
        ("ftp://maps.google.com/?q=28.6,77.2", maps.NOT_A_LINK),
        ("28.6129, 77.2295", maps.TYPED_COORDINATES),
        ("https://www.google.com/maps/place/Taj+Mahal/", maps.NO_PIN),
        ("https://maps.google.com/?q=28.6,77.2 extra words", maps.NO_PIN),
        ("https://maps.google.com/?q=28.6,77.2\textra", maps.NOT_A_LINK),
    ],
)
def test_resolve_refuses_with_a_reason(text: str, message: str) -> None:
    with pytest.raises(MapsInputError) as caught:
        resolve(text)
    assert str(caught.value) == message


# --- Plus codes ------------------------------------------------------------------------------

# Copied from github.com/google/open-location-code test_data/decoding.csv (Apache-2.0):
# code, latLo, lngLo, latHi, lngHi.
DECODING = [
    ("7FG49QCJ+2V", 20.37, 2.782125, 20.370125, 2.78225),
    ("7FG49QCJ+2VX", 20.3701, 2.78221875, 20.370125, 2.78225),
    ("7FG49QCJ+2VXGJ", 20.370113, 2.782234375, 20.370114, 2.78223632813),
    ("8FVC2222+22", 47.0, 8.0, 47.000125, 8.000125),
    ("4VCPPQGP+Q9", -41.273125, 174.785875, -41.273, 174.786),
    ("62G20000+", 0.0, -180.0, 1, -179),
    ("22220000+", -90, -180, -89, -179),
    ("6VGX0000+", 0, 179, 1, 180),
    ("CFX3X2X2+X2", 89.9998750, 1, 90, 1.0001250),
    ("84000000+", 30, -140, 50, -120),
    ("849VGJQF+VX7QR3J", 37.5396691200, -122.3750698242, 37.5396691600, -122.3750697021),
    ("5PVX2JXR+R6G29VC", -12.95044812, 119.640568847656, -12.95044808, 119.640568969727),
    ("55CJG366+PP", -21.48825, -107.93825, -21.488125, -107.938125),
    ("96QQM963+G8J", 65.661325, -84.64675, 65.66135, -84.64671875),
    ("4VXPHWHV+", -30.4225, 174.9425, -30.42, 174.945),
]


@pytest.mark.parametrize(("code", "lat_lo", "lng_lo", "lat_hi", "lng_hi"), DECODING)
def test_plus_code_decoding_matches_the_reference(
    code: str, lat_lo: float, lng_lo: float, lat_hi: float, lng_hi: float
) -> None:
    area = pluscode.decode(code)
    assert area.lat_lo == pytest.approx(lat_lo, abs=1e-10)
    assert area.lng_lo == pytest.approx(lng_lo, abs=1e-10)
    assert area.lat_hi == pytest.approx(lat_hi, abs=1e-10)
    assert area.lng_hi == pytest.approx(lng_hi, abs=1e-10)


# From validityTests.csv: code, is_valid, is_short, is_full.
VALIDITY = [
    ("8FWC2345+G6", True, False, True),
    ("8FWC2345+G6G", True, False, True),
    ("8fwc2345+", True, False, True),
    ("8FWCX400+", True, False, True),
    ("WC2345+G6g", True, True, False),
    ("2345+G6", True, True, False),
    ("45+G6", True, True, False),
    ("+G6", True, True, False),
    ("G+", False, False, False),
    ("+", False, False, False),
    ("8FWC2345+G", False, False, False),
    ("8FWC2_45+G6", False, False, False),
    ("8FWC2η45+G6", False, False, False),
    ("8FWC2345+G6+", False, False, False),
    ("8FWC2345G6+", False, False, False),
    ("8FWC2300+G6", False, False, False),
    ("WC2300+G6g", False, False, False),
    ("WC2345+G", False, False, False),
    ("WC2300+", False, False, False),
    ("84900000+", False, False, False),
    ("849VGJQF+VX7QR3J", True, False, True),
    ("849VGJQF+VX7QR3U", False, False, False),
]


@pytest.mark.parametrize(("code", "valid", "short", "full"), VALIDITY)
def test_plus_code_validity_matches_the_reference(
    code: str, valid: bool, short: bool, full: bool
) -> None:
    assert pluscode.is_valid(code) is valid
    assert pluscode.is_short(code) is short
    assert pluscode.is_full(code) is full


def test_resolve_full_plus_code_with_or_without_a_place_name() -> None:
    for text in ("8FVC2222+22", "8fvc2222+22", "8FVC2222+22 Zurich, Switzerland"):
        pin = resolve(text)
        assert pin.source == "plus_code"
        assert pin.lat == pytest.approx(47.0000625, abs=1e-6)
        assert pin.lng == pytest.approx(8.0000625, abs=1e-6)
        assert pin.resolved_url is None
        assert pin.plus_code == "8FVC2222+22"


def test_resolve_returns_the_plus_code_alone() -> None:
    pin = resolve("7JWV8XX8+XX Sector 150, Noida, Uttar Pradesh 201310")
    assert pin.plus_code == "7JWV8XX8+XX"
    assert resolve("https://maps.google.com/?q=28.5,77.3").plus_code is None


def test_resolve_pasted_link_with_a_space_after_the_comma() -> None:
    pin = resolve("https://www.google.com/maps/search/28.535516, 77.391026")
    assert (pin.lat, pin.lng) == (28.535516, 77.391026)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("8XX8+XX Noida", maps.SHORT_PLUS_CODE),
        ("2222+22", maps.SHORT_PLUS_CODE),
        ("8FWC2300+G6", maps.BAD_PLUS_CODE),
        ("8FVC2222+", maps.ROUGH_PLUS_CODE),
        ("8FVC0000+", maps.ROUGH_PLUS_CODE),
    ],
)
def test_plus_codes_that_cannot_be_placed(text: str, message: str) -> None:
    with pytest.raises(MapsInputError) as caught:
        resolve(text)
    assert str(caught.value) == message


# --- Short links: followed hop by hop with a fake client (SSRF rules) ------------------------


class FakeGoogle:
    """A fake web: url → (status, location or None). Records every URL requested."""

    def __init__(self, routes: dict[str, tuple[int, str | None]], delay: float = 0.0) -> None:
        self.routes = routes
        self.delay = delay
        self.requested: list[str] = []
        self.body_read = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requested.append(str(request.url))
        if self.delay:
            time.sleep(self.delay)
        status, location = self.routes.get(str(request.url), (404, None))
        headers = {"location": location} if location else {}
        return httpx.Response(status, headers=headers, stream=_Body(self))

    def factory(self) -> Callable[[], httpx.Client]:
        return lambda: httpx.Client(transport=httpx.MockTransport(self.handler))


class _Body(httpx.SyncByteStream):
    """A response body that notes whether anyone read it (SECURITY rule 3: nobody should)."""

    def __init__(self, owner: FakeGoogle) -> None:
        self.owner = owner

    def __iter__(self) -> Iterator[bytes]:
        self.owner.body_read = True
        yield b"<html>a large page we must never download</html>"


SHORT = "https://maps.app.goo.gl/AbCdEf123"
LONG_WITH_PIN = "https://www.google.com/maps/place/X/@28.60,77.20,17z/data=!3m1!8m2!3d28.61!4d77.21"


def test_short_link_stops_at_the_first_location_with_a_pin() -> None:
    fake = FakeGoogle({SHORT: (302, LONG_WITH_PIN)})
    pin = resolve(SHORT, client_factory=fake.factory())
    assert (pin.lat, pin.lng, pin.source) == (28.61, 77.21, "short_link")
    assert pin.resolved_url == LONG_WITH_PIN
    assert fake.requested == [SHORT]  # Google's page itself is never fetched
    assert fake.body_read is False


def test_short_link_chain_is_followed_over_https() -> None:
    fake = FakeGoogle(
        {
            "https://goo.gl/maps/xyz": (301, "https://maps.app.goo.gl/next"),
            "https://maps.app.goo.gl/next": (302, "https://maps.google.com/?q=28.5,77.3"),
        }
    )
    pin = resolve("http://goo.gl/maps/xyz", client_factory=fake.factory())
    assert (pin.lat, pin.lng) == (28.5, 77.3)
    assert fake.requested == ["https://goo.gl/maps/xyz", "https://maps.app.goo.gl/next"]


def test_short_link_to_a_dropped_pin() -> None:
    dropped = "https://www.google.com/maps/search/28.535516,+77.391026?entry=tts&g_ep=EgoyMDI2"
    fake = FakeGoogle({SHORT: (302, dropped)})
    pin = resolve(SHORT, client_factory=fake.factory())
    assert (pin.lat, pin.lng, pin.source) == (28.535516, 77.391026, "short_link")
    assert pin.resolved_url == dropped and pin.plus_code is None
    assert fake.requested == [SHORT]


def test_relative_location_resolves_against_the_current_host() -> None:
    fake = FakeGoogle({SHORT: (302, "/?q=28.5,77.3")})
    pin = resolve(SHORT, client_factory=fake.factory())
    assert pin.resolved_url == "https://maps.app.goo.gl/?q=28.5,77.3"
    assert (pin.lat, pin.lng) == (28.5, 77.3)


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.example/maps/@28.6,77.2,15z",  # another host
        "http://www.google.com/maps/@28.6,77.2,15z",  # downgrade to http
        "https://www.google.com/url?q=https://evil.example",  # Google's open redirect
        "https://maps.google.com:8443/?q=28.6,77.2",  # another port
        "https://user@maps.google.com/?q=28.6,77.2",  # user-info
        "https://169.254.169.254/latest/meta-data",  # cloud metadata address
        "https://maps.google.com\\@evil.example/",  # parsers disagree on the host
    ],
)
def test_a_hop_off_the_allowlist_is_never_followed(location: str) -> None:
    fake = FakeGoogle({SHORT: (302, location)})
    with pytest.raises(MapsInputError) as caught:
        resolve(SHORT, client_factory=fake.factory())
    assert str(caught.value) == maps.LEFT_GOOGLE
    assert fake.requested == [SHORT]


def _chain(redirects: int, last: str) -> dict[str, tuple[int, str | None]]:
    hops = [f"https://maps.app.goo.gl/hop{i}" for i in range(redirects)]
    routes: dict[str, tuple[int, str | None]] = {}
    for index, hop in enumerate(hops):
        routes[hop] = (302, hops[index + 1] if index + 1 < len(hops) else last)
    return routes


def test_five_redirects_are_followed() -> None:
    fake = FakeGoogle(_chain(5, "https://maps.google.com/?q=28.5,77.3"))
    pin = resolve("https://maps.app.goo.gl/hop0", client_factory=fake.factory())
    assert (pin.lat, pin.lng) == (28.5, 77.3)
    assert len(fake.requested) == 5


def test_a_sixth_redirect_is_refused() -> None:
    fake = FakeGoogle(_chain(6, "https://maps.google.com/?q=28.5,77.3"))
    with pytest.raises(MapsInputError) as caught:
        resolve("https://maps.app.goo.gl/hop0", client_factory=fake.factory())
    assert str(caught.value) == maps.TOO_MANY_REDIRECTS
    assert len(fake.requested) == 6


def test_redirect_loops_end_at_the_limit() -> None:
    fake = FakeGoogle({SHORT: (302, SHORT)})
    with pytest.raises(MapsInputError) as caught:
        resolve(SHORT, client_factory=fake.factory())
    assert str(caught.value) == maps.TOO_MANY_REDIRECTS


@pytest.mark.parametrize(
    ("status", "message"), [(404, maps.LINK_BROKEN), (500, maps.LINK_BROKEN), (200, maps.NO_PIN)]
)
def test_dead_ends(status: int, message: str) -> None:
    fake = FakeGoogle({SHORT: (status, None)})
    with pytest.raises(MapsInputError) as caught:
        resolve(SHORT, client_factory=fake.factory())
    assert str(caught.value) == message
    assert fake.body_read is False


def test_the_whole_lookup_has_one_time_budget() -> None:
    fake = FakeGoogle({SHORT: (302, LONG_WITH_PIN)}, delay=1.0)
    started = time.monotonic()
    with pytest.raises(MapsInputError) as caught:
        resolve(SHORT, client_factory=fake.factory(), timeout_seconds=0.2)
    assert str(caught.value) == maps.TOO_SLOW
    assert time.monotonic() - started < 0.9


def test_network_errors_are_a_staff_message() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(broken))

    with pytest.raises(MapsInputError) as caught:
        resolve(SHORT, client_factory=factory)
    assert str(caught.value) == maps.UNREACHABLE


def test_the_production_client_never_follows_redirects_itself() -> None:
    """SECURITY rule 2: redirects are only ever followed by our own checked loop."""
    client = REAL_DEFAULT_CLIENT()  # building a client makes no network call
    try:
        assert client.follow_redirects is False
        assert client.timeout.read == maps.TIMEOUT_SECONDS
    finally:
        client.close()


# --- Endpoint --------------------------------------------------------------------------------

URL = "/api/v1/admin/maps/resolve"


def test_endpoint_resolves_a_long_link(owner: SignedIn) -> None:
    response = owner.client.post(
        URL, json={"input": "https://maps.google.com/?q=28.5,77.3"}, headers=owner.headers()
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "lat": 28.5,
        "lng": 77.3,
        "source": "url_coordinates",
        "resolved_url": "https://maps.google.com/?q=28.5,77.3",
        "plus_code": None,
    }


def test_endpoint_returns_the_plus_code_the_cms_can_save(owner: SignedIn) -> None:
    text = "7JWV8XX8+XX Sector 150, Noida, Uttar Pradesh 201310"
    pin = ok_json(owner.client.post(URL, json={"input": text}, headers=owner.headers()))
    assert (pin["source"], pin["plus_code"], pin["resolved_url"]) == (
        "plus_code",
        "7JWV8XX8+XX",
        None,
    )


def ok_json(response: httpx.Response) -> dict[str, object]:
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_endpoint_follows_short_links_with_the_injected_client(
    owner: SignedIn, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeGoogle({SHORT: (302, LONG_WITH_PIN)})
    monkeypatch.setattr(routes_catalogue, "resolver_client", fake.factory())
    response = owner.client.post(URL, json={"input": SHORT}, headers=owner.headers())
    assert response.status_code == 200, response.text
    assert response.json()["source"] == "short_link"
    assert response.json()["lat"] == 28.61


def test_endpoint_explains_short_plus_codes(owner: SignedIn) -> None:
    response = owner.client.post(URL, json={"input": "8XX8+XX Noida"}, headers=owner.headers())
    assert response.status_code == 422
    body = response.json()
    assert body["errors"] == [{"field": "input", "message": maps.SHORT_PLUS_CODE}]
    assert "full code" in body["detail"]


def test_endpoint_validates_length(owner: SignedIn) -> None:
    too_long = "https://maps.google.com/?q=" + "1" * 2100
    response = owner.client.post(URL, json={"input": too_long}, headers=owner.headers())
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "input"


def test_endpoint_needs_projects_write(app: FastAPI) -> None:
    sales = new_client(app)
    signed = sign_in(sales, make_user("sales"))
    body = {"input": "https://maps.google.com/?q=28.5,77.3"}
    assert sales.post(URL, json=body, headers=signed.headers()).status_code == 403
    editor = new_client(app)
    signed = sign_in(editor, make_user("content_editor"))
    assert editor.post(URL, json=body, headers=signed.headers()).status_code == 200


def test_endpoint_is_rate_limited_per_person(owner: SignedIn) -> None:
    body = {"input": "https://maps.google.com/?q=28.5,77.3"}
    codes = [
        owner.client.post(URL, json=body, headers=owner.headers()).status_code
        for _ in range(routes_catalogue.MAPS_LIMIT + 1)
    ]
    assert codes[:-1] == [200] * routes_catalogue.MAPS_LIMIT
    assert codes[-1] == 429
