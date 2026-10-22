"""Cloudinary-compatible signatures: signing upload parameters and checking reply signatures.

Both stores use these functions: the Cloudinary store with the account's API secret, the fake
store with its fixed public test key, so the fake store checks a direct upload exactly as
Cloudinary would.

How Cloudinary signs (cloudinary.com/documentation/authentication_signatures and
/response_signatures, read 23 Oct 2026; tested in tests/test_media_signing.py):
  1. Upload request: every parameter sent except `file`, `cloud_name`, `resource_type` and
     `api_key`, as `name=value` pairs sorted by name and joined with `&`, then the API secret
     appended; the hex SHA-1 or SHA-256 of that string. Cloudinary accepts either digest; a
     signature stays valid for one hour after its `timestamp`.
  2. Upload reply: the same recipe over `public_id` and `version` only.

WHY the SDK's own function underneath: one implementation of the encoding rules (the SDK's
"signature version 2" escapes `&` inside values), maintained by Cloudinary.
SECURITY: comparisons are constant-time; never compare signatures with `==`.
"""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from typing import Any, Final

from empire_api.media.store import InvalidReplyError, ReplyRef

# Not part of the signature (Cloudinary's rule above), plus the signature itself.
UNSIGNED_FIELDS: Final = frozenset({"file", "cloud_name", "resource_type", "api_key", "signature"})
SHA1_HEX: Final = 40
SHA256_HEX: Final = 64
# WHY SHA-256 for our requests: Cloudinary accepts it as well as SHA-1, and it is the stronger
# digest. Replies may come back in either, so verification accepts both (by length).
REQUEST_ALGORITHM: Final = "sha256"


def _sign(params: Mapping[str, Any], secret: str, algorithm: str, version: int) -> str:
    # WHY imported here: the SDK reads CLOUDINARY_URL from the environment when it is first
    # imported and raises on a malformed value; config.py reports that more clearly first.
    from cloudinary.utils import api_sign_request  # noqa: PLC0415

    signature: str = api_sign_request(dict(params), secret, algorithm, version)
    return signature


def _algorithm(signature: str) -> str | None:
    return {SHA1_HEX: "sha1", SHA256_HEX: "sha256"}.get(len(signature))


def sign_params(params: Mapping[str, Any], secret: str, algorithm: str = REQUEST_ALGORITHM) -> str:
    """Signature for upload parameters (`UNSIGNED_FIELDS` are left out automatically)."""
    to_sign = {k: v for k, v in params.items() if k not in UNSIGNED_FIELDS}
    return _sign(to_sign, secret, algorithm, 2)


def params_signature_ok(params: Mapping[str, Any], signature: str, secret: str) -> bool:
    """Whether `signature` signs these upload parameters (SHA-1 or SHA-256)."""
    algorithm = _algorithm(signature)
    if algorithm is None:
        return False
    return hmac.compare_digest(sign_params(params, secret, algorithm), signature)


def reply_signature(public_id: str, version: int | str, secret: str, algorithm: str) -> str:
    """The signature a store puts on an upload reply (public id and version only).

    WHY signature version 1: that is how Cloudinary signs replies (the SDK's own
    `verify_api_response_signature` uses it).
    """
    return _sign({"public_id": public_id, "version": version}, secret, algorithm, 1)


def reply_signature_ok(public_id: str, version: int | str, signature: str, secret: str) -> bool:
    algorithm = _algorithm(signature)
    if algorithm is None:
        return False
    expected = reply_signature(public_id, version, secret, algorithm)
    return hmac.compare_digest(expected, signature)


def verified_reply(reply: Mapping[str, Any], secret: str) -> ReplyRef:
    """Public id and version of a direct-upload reply whose signature checks out.

    SECURITY: the signature covers only these two fields, so nothing else in the reply (bytes,
    format, …) is trusted; uploads.confirm re-reads the asset from the store instead.

    Raises:
        InvalidReplyError: a field is missing or malformed, or the signature doesn't match.
    """
    public_id, version, signature = (
        reply.get("public_id"),
        reply.get("version"),
        reply.get("signature"),
    )
    if not isinstance(public_id, str) or not 0 < len(public_id) <= 255:
        raise InvalidReplyError("public_id")
    if isinstance(version, str) and version.isdecimal():
        version = int(version)
    if not isinstance(version, int) or isinstance(version, bool) or version <= 0:
        raise InvalidReplyError("version")
    if not isinstance(signature, str) or not reply_signature_ok(
        public_id, version, signature, secret
    ):
        raise InvalidReplyError("signature")
    return ReplyRef(public_id=public_id, version=version)
