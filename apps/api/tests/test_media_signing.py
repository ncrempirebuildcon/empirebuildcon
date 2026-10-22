"""Cloudinary-compatible signatures (media/signing.py), checked against the vectors on
cloudinary.com/documentation/authentication_signatures and /response_signatures (read
23 Oct 2026) and against an independent hashlib computation of the documented recipe."""

from __future__ import annotations

import hashlib

import pytest

from empire_api.media import signing
from empire_api.media.cloudinary_store import CloudinaryStore
from empire_api.media.credentials import CloudinaryCredentials, parse_cloudinary_url
from empire_api.media.store import InvalidReplyError

DOCS_SECRET = "abcd"  # the documentation's example secret
DOCS_TIMESTAMP = "1315060510"


def test_upload_signature_matches_the_documented_examples() -> None:
    simple = signing.sign_params({"timestamp": DOCS_TIMESTAMP}, DOCS_SECRET, "sha1")
    assert simple == "a21ad0f63beb4de2e5575204b79ab90bffb02c10"
    eager = signing.sign_params(
        {
            "timestamp": DOCS_TIMESTAMP,
            "public_id": "sample_image",
            "eager": "w_400,h_300,c_pad|w_260,h_200,c_crop",
        },
        DOCS_SECRET,
        "sha1",
    )
    assert eager == "bfd09f95f331f558cbd1320e67aa8d488770583e"


def test_file_cloud_name_resource_type_and_api_key_are_not_signed() -> None:
    base = {"timestamp": DOCS_TIMESTAMP, "public_id": "sample_image"}
    extra = {
        **base,
        "file": "x",
        "cloud_name": "demo",
        "resource_type": "raw",
        "api_key": "123",
        "signature": "old",
    }
    assert signing.sign_params(extra, DOCS_SECRET) == signing.sign_params(base, DOCS_SECRET)


def test_sha256_is_the_documented_recipe() -> None:
    expected = hashlib.sha256(f"timestamp={DOCS_TIMESTAMP}{DOCS_SECRET}".encode()).hexdigest()
    assert signing.sign_params({"timestamp": DOCS_TIMESTAMP}, DOCS_SECRET) == expected


def test_signature_check_accepts_both_digests_and_nothing_else() -> None:
    params = {"timestamp": DOCS_TIMESTAMP, "folder": "empire/test/video", "public_id": "x"}
    for algorithm in ("sha1", "sha256"):
        good = signing.sign_params(params, DOCS_SECRET, algorithm)
        assert signing.params_signature_ok(params, good, DOCS_SECRET)
        assert not signing.params_signature_ok({**params, "public_id": "y"}, good, DOCS_SECRET)
        assert not signing.params_signature_ok(params, good, "other-secret")
    assert not signing.params_signature_ok(params, "abc", DOCS_SECRET)
    assert not signing.params_signature_ok(params, "", DOCS_SECRET)


def test_reply_signature_follows_the_documented_recipe() -> None:
    """WHY computed, not copied: the response_signatures page's printed SHA-1
    (b4ad47fb…, read 23 Oct 2026) is the hash of `public_id=sample_image&timestamp=…abcd`, an
    upload string, not of the `public_id=sample&version=1315060510abcd` string it shows. The
    recipe itself (public_id and version, sorted, secret appended) is what we check here; the
    SDK's own verify_api_response_signature uses the same recipe."""
    documented_string = f"public_id=sample&version={DOCS_TIMESTAMP}{DOCS_SECRET}"
    expected = hashlib.sha1(documented_string.encode()).hexdigest()  # noqa: S324 — Cloudinary's
    assert expected == "912d90b6fe28aa6820cf928bc440a65a0f36e002"
    assert signing.reply_signature("sample", DOCS_TIMESTAMP, DOCS_SECRET, "sha1") == expected
    assert signing.reply_signature_ok("sample", 1315060510, expected, DOCS_SECRET)
    assert not signing.reply_signature_ok("sample", 1315060511, expected, DOCS_SECRET)


def test_verified_reply_reads_only_public_id_and_version() -> None:
    good = {
        "public_id": "empire/test/video/abc",
        "version": 1712000000,
        "signature": signing.reply_signature("empire/test/video/abc", 1712000000, "s", "sha1"),
        "bytes": 999_999_999,  # not covered by the signature, so never trusted
    }
    ref = signing.verified_reply(good, "s")
    assert (ref.public_id, ref.version) == ("empire/test/video/abc", 1712000000)
    assert signing.verified_reply({**good, "version": "1712000000"}, "s").version == 1712000000
    for broken in (
        {**good, "version": 1712000001},
        {**good, "public_id": "empire/test/video/other"},
        {**good, "signature": None},
        {**good, "version": True},
        {**good, "public_id": "x" * 300},
        {k: v for k, v in good.items() if k != "signature"},
    ):
        with pytest.raises(InvalidReplyError):
            signing.verified_reply(broken, "s")


def test_cloudinary_store_signs_a_scoped_direct_upload() -> None:
    store = CloudinaryStore(CloudinaryCredentials("demo", "key-123", "secret-xyz"))
    signed = store.sign_upload(
        resource_type="video",
        folder="empire/test/video",
        public_id="0192-uuid",
        allowed_formats=("mp4", "mov", "webm"),
    )
    assert signed.upload_url == "https://api.cloudinary.com/v1_1/demo/video/upload"
    fields = signed.fields
    assert fields["api_key"] == "key-123" and fields["signature"] == signed.signature
    assert (fields["folder"], fields["public_id"]) == ("empire/test/video", "0192-uuid")
    # SECURITY: overwrite=false, so the signature (valid an hour at Cloudinary) can't replace
    # the file after it was checked; the poster is made eagerly (Free plan: 40 MB on the fly).
    assert fields["overwrite"] == "false"
    assert fields["allowed_formats"] == "mp4,mov,webm"
    assert fields["eager"] == "so_auto/c_limit,h_480,w_480/jpg"
    assert fields["eager_async"] == "true"
    assert "secret-xyz" not in str(fields)
    assert signing.params_signature_ok(fields, signed.signature, "secret-xyz")


def test_raw_uploads_sign_no_format_list() -> None:
    store = CloudinaryStore(CloudinaryCredentials("demo", "k", "s"))
    signed = store.sign_upload(
        resource_type="raw", folder="f", public_id="x.docx", allowed_formats=("docx",)
    )
    assert "allowed_formats" not in signed.fields and "eager" not in signed.fields


def test_credentials_parse_and_never_show_the_secret() -> None:
    parsed = parse_cloudinary_url("cloudinary://1234:abc-DEF_9@My_Cloud")
    assert (parsed.cloud_name, parsed.api_key, parsed.api_secret) == (
        "My_Cloud",
        "1234",
        "abc-DEF_9",
    )
    assert "abc-DEF_9" not in repr(parsed)
    for broken in (
        "https://k:s@demo",
        "cloudinary://k@demo",
        "cloudinary://:s@demo",
        "cloudinary://k:s@",
    ):
        with pytest.raises(ValueError, match="CLOUDINARY_URL") as raised:
            parse_cloudinary_url(broken)
        assert "s@" not in str(raised.value)
