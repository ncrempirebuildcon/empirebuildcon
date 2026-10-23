"""The photo check (media/sniff.py): magic bytes decide, never the name or the browser's type;
SVG, HEIC and GIF are refused; files that only start like an image fail; 25 megapixels max."""

from __future__ import annotations

import pytest

from empire_api.media import sniff
from media_support import MP4, PDF, big_png, ftyp, image_bytes


@pytest.mark.parametrize(
    ("pillow_format", "expected"),
    [("JPEG", "jpg"), ("PNG", "png"), ("WEBP", "webp"), ("AVIF", "avif")],
)
def test_accepted_formats_and_their_size(pillow_format: str, expected: str) -> None:
    info = sniff.inspect_image(image_bytes(pillow_format, (40, 30)))
    assert (info.format, info.width, info.height) == (expected, 40, 30)


@pytest.mark.parametrize(
    ("data", "words"),
    [
        (b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"/>', "SVG"),
        (b"\xef\xbb\xbf  <svg onload='alert(1)'></svg>", "SVG"),
        (b"<!DOCTYPE html><html><body><svg></svg></body></html>", "SVG"),
        (ftyp(b"heic", b"mif1", b"heic"), "HEIC"),
        (ftyp(b"mif1", b"mif1", b"heic"), "HEIC"),
        (b"GIF89a\x01\x00\x01\x00" + b"\x00" * 20, "GIF"),
        (PDF, "isn't a JPEG"),
        (MP4, "isn't a JPEG"),
        (b"", "isn't a JPEG"),
    ],
)
def test_refused_formats_say_why(data: bytes, words: str) -> None:
    with pytest.raises(sniff.NotAnImageError, match=words):
        sniff.inspect_image(data)


@pytest.mark.parametrize(
    "data",
    [
        b"\xff\xd8\xff<html><script>alert(1)</script></html>",  # JPEG magic, then HTML
        b"\x89PNG\r\n\x1a\n<script>alert(1)</script>" + b"\x00" * 40,  # PNG magic, no chunks
        b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 40,  # WebP header, no image
        image_bytes("PNG")[:40],  # a real PNG cut short
        ftyp(b"avif", b"avif", b"mif1"),  # AVIF brand, no image inside
    ],
)
def test_files_that_only_start_like_an_image_are_refused(data: bytes) -> None:
    with pytest.raises(sniff.NotAnImageError, match="damaged"):
        sniff.inspect_image(data)


def test_more_than_25_megapixels_is_refused() -> None:
    with pytest.raises(sniff.TooManyPixelsError):
        sniff.inspect_image(big_png(6000, 5000))  # 30 MP


def test_exactly_25_megapixels_passes() -> None:
    info = sniff.inspect_image(big_png(5000, 5000))
    assert (info.width, info.height) == (5000, 5000)


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (PDF, "pdf"),
        (MP4, "mp4"),
        (ftyp(b"qt  ", b"qt  "), "mov"),
        (b"\x1a\x45\xdf\xa3" + b"\x00" * 20, "webm"),
        (image_bytes(), None),
        (b"plain text", None),
    ],
)
def test_direct_upload_formats(data: bytes, expected: str | None) -> None:
    assert sniff.detect_direct_format(data[:64]) == expected
