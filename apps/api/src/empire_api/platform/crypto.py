"""Small crypto and network helpers: client IP, IP hashing/masking, token hashing, HMAC tokens.

Collaborators: users/ (login rate limits, CSRF, reset tokens), platform/audit.py (masked IPs).
Implements: SECURITY.md §1 (hashed reset tokens; limits per network, an IPv6 /64 counting as one),
§8 (IPs stored only as a salted hash on leads; audit rows keep a masked network, enough to
investigate abuse).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import secrets

from starlette.requests import Request

from empire_api.config import get_settings

CLIENT_IP_HEADER = "x-empire-client-ip"


def client_ip(request: Request) -> str:
    """The visitor's IP address, for rate limits and audit rows.

    SECURITY: X-Forwarded-For can be forged by the visitor, so we never read it. Our own web
    proxy (apps/web/src/proxy.ts) puts the address the hosting platform saw into
    `X-Empire-Client-IP`, and we believe that header only on requests that passed the edge-key
    check (middleware/edge_guard.py). Without an edge key (local dev) we use the socket address.
    Getting this wrong lets an attacker rotate fake IPs to dodge rate limits, or lets one
    address block every staff login.
    """
    peer = request.client.host if request.client else "0.0.0.0"  # noqa: S104 — placeholder only
    if not request.scope.get("empire_edge_verified"):
        return peer
    candidate = request.headers.get(CLIENT_IP_HEADER, "").strip()
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return peer
    return candidate


IPV6_NETWORK_PREFIX = 64


def network_key(ip: str) -> str:
    """The network an address stands for, for rate limits and lockouts.

    SECURITY: one IPv6 customer usually gets a whole /64 (2^64 addresses), so limiting single
    IPv6 addresses would let anyone dodge every limit by changing the last bits. IPv4 stays as is;
    IPv6 becomes its /64 prefix; an IPv4-mapped IPv6 address becomes its IPv4 address. Anything
    unparseable is returned unchanged (it still gets its own counter).
    """
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        prefix = f"{address}/{IPV6_NETWORK_PREFIX}"
        return str(ipaddress.ip_network(prefix, strict=False))
    return str(address)


def hash_ip(ip: str) -> str:
    """Salted, keyed hash of an IP for rate-limit keys and abuse checks (not reversible)."""
    salt = get_settings().ip_hash_salt.get_secret_value().encode()
    return hmac.new(salt, ip.encode(), hashlib.sha256).hexdigest()[:32]


def mask_ip(ip: str | None) -> str | None:
    """Keep the network, drop the host: 203.0.113.42 → 203.0.113.0/24; IPv6 → /48."""
    if not ip:
        return None
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return None
    prefix = 24 if address.version == 4 else 48
    return str(ipaddress.ip_network(f"{address}/{prefix}", strict=False))


def new_token(num_bytes: int = 32) -> str:
    """A URL-safe random token (reset links, setup links)."""
    return secrets.token_urlsafe(num_bytes)


def hash_token(token: str) -> str:
    """SHA-256 of a token. We store only this, so a database leak doesn't leak working links."""
    return hashlib.sha256(token.encode()).hexdigest()


def keyed_digest(purpose: str, value: str) -> str:
    """HMAC of `value` under SESSION_SECRET, separated by `purpose` (e.g. CSRF tokens)."""
    key = get_settings().session_secret.get_secret_value().encode()
    mac = hmac.new(key, f"{purpose}:{value}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode()


def data_digest(purpose: str, value: str) -> str:
    """Hex HMAC-SHA256 of `value` under a key derived from DATA_ENCRYPTION_KEY, per `purpose`.

    For values we must recognise but never read back: two-factor recovery codes, and the
    recipient of an email in the sent-mail log (mail/models.py).

    SECURITY / WHY this key and not SESSION_SECRET: the runbook rotates SESSION_SECRET to sign
    everyone out (SECURITY.md §11); that must not also void every recovery code. Rotating
    DATA_ENCRYPTION_KEY already means re-enrolling two-factor (the TOTP secrets are encrypted
    with it), so tying these digests to it adds no new break. WHY keyed: a recovery code has
    50 bits of randomness; an unkeyed hash of it could be brute-forced from a database copy.
    """
    raw = get_settings().data_encryption_key.get_secret_value().encode()
    key = hashlib.sha256(b"empire data digest:" + purpose.encode() + b":" + raw).digest()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    """Compare secrets without leaking how many leading characters matched."""
    return hmac.compare_digest(a.encode(), b.encode())
