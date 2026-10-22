"""Small crypto and network helpers: client IP, IP hashing/masking, token hashing, HMAC tokens.

Collaborators: users/ (login rate limits, CSRF, reset tokens), platform/audit.py (masked IPs).
Implements: SECURITY.md §1 (hashed reset tokens), §8 (IPs stored only as a salted hash on
leads; audit rows keep a masked network, enough to investigate abuse).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import secrets

from starlette.requests import Request

from empire_api.config import get_settings


def client_ip(request: Request) -> str:
    """The visitor's IP address as seen by the first proxy we trust.

    SECURITY: X-Forwarded-For is client-controlled at its left end. We only trust the last
    `TRUSTED_PROXY_HOPS` entries, which our own proxies appended. With 0 hops (local dev) we use
    the socket peer. Getting this wrong lets an attacker rotate fake IPs to dodge rate limits.
    """
    hops = get_settings().trusted_proxy_hops
    peer = request.client.host if request.client else "0.0.0.0"  # noqa: S104 — placeholder only
    if hops == 0:
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    chain = [part.strip() for part in forwarded.split(",") if part.strip()]
    if len(chain) >= hops:
        candidate = chain[-hops]
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            return peer
        return candidate
    return peer


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


def constant_time_equals(a: str, b: str) -> bool:
    """Compare secrets without leaking how many leading characters matched."""
    return hmac.compare_digest(a.encode(), b.encode())
