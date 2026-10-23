"""What a file really is, from its first bytes: the photo check of POST /admin/media/images and
the fake store's format detection.

Collaborators: uploads.py (photos), fake_store.py and routes_dev.py (direct uploads).
Implements: SECURITY.md §6 (magic-byte check; JPEG, PNG, WebP and AVIF only; no SVG uploads),
D-007 (25 megapixels on Cloudinary Free).

How the photo check works:
  1. Read the signature bytes. JPEG, PNG, WebP and AVIF pass; SVG, HEIC, GIF and anything else
     are refused (415). The filename and the browser's type are never consulted.
  2. Open the bytes with Pillow, allowing only the detected format, and read the size from the
     header. A file that only *starts* like an image (a polyglot or a truncated file) fails here.
  3. Refuse more than 25 megapixels (422) before Pillow decodes anything, refuse animations
     (not photos), then let Pillow verify the data.
Embedded metadata (EXIF/GPS, XMP, …) is removed afterwards by scrub.py.

SECURITY: SVG can carry script, which is why it never passes (the logo kit's SVGs ship in code).
"""

from __future__ import annotations

import io
import warnings
from dataclasses import dataclass
from typing import Final

from PIL import Image, UnidentifiedImageError

from empire_api.media.vocab import MAX_IMAGE_PIXELS

# Pillow's plugin names for our formats.
PILLOW_FORMATS: Final = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP", "avif": "AVIF"}
# HEIC/HEVC brands. `mif1` alone is generic HEIF (AVIF files list it too), so it decides nothing.
_HEIC_BRANDS: Final = frozenset({b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis"})
_AVIF_BRANDS: Final = frozenset({b"avif", b"avis"})


class NotAnImageError(ValueError):
    """Not one of the accepted photo formats. The message is safe to show to staff."""


class TooManyPixelsError(ValueError):
    """Above the store's megapixel limit."""


@dataclass(frozen=True)
class ImageInfo:
    format: str  # jpg | png | webp | avif
    width: int
    height: int


def _ftyp_brands(head: bytes) -> tuple[bytes, set[bytes]] | None:
    """(major brand, all brands) of an ISO-BMFF file (AVIF, HEIC, MP4, MOV), else None."""
    if len(head) < 16 or head[4:8] != b"ftyp":
        return None
    size = int.from_bytes(head[0:4], "big")
    end = min(size if size >= 16 else 16, len(head))
    major = head[8:12]
    compatible = {head[i : i + 4] for i in range(16, end - 3, 4)}
    return major, {major, *compatible}


def detect_image_format(head: bytes) -> str:
    """jpg | png | webp | avif from the first bytes, or NotAnImageError saying what it is."""
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[0:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    brands = _ftyp_brands(head)
    if brands is not None:
        _major, every = brands
        if every & _HEIC_BRANDS:
            raise NotAnImageError(
                "HEIC photos aren't supported. Export the photo as JPEG and upload it again."
            )
        if every & _AVIF_BRANDS:
            return "avif"
    if head.startswith((b"GIF87a", b"GIF89a")):
        raise NotAnImageError("GIF images aren't supported. Use JPEG, PNG, WebP or AVIF.")
    if _looks_like_svg(head):
        raise NotAnImageError("SVG images can't be uploaded. Use JPEG, PNG, WebP or AVIF.")
    raise NotAnImageError("This file isn't a JPEG, PNG, WebP or AVIF image.")


def _looks_like_svg(head: bytes) -> bool:
    text = head.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    return text.startswith((b"<?xml", b"<svg", b"<!doctype svg")) or b"<svg" in text[:1024]


def inspect_image(data: bytes) -> ImageInfo:
    """Check a photo and read its size (steps 1–3 in the module header).

    Raises:
        NotAnImageError: not an accepted format, or the data doesn't decode as one.
        TooManyPixelsError: more than 25 megapixels.
    """
    image_format = detect_image_format(data[:64])  # 1
    try:
        with warnings.catch_warnings():
            # Pillow warns (and later raises) on huge images; we refuse them ourselves below.
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=[PILLOW_FORMATS[image_format]]) as image:
                width, height = image.size  # 2: header only, nothing decoded yet
                if width * height > MAX_IMAGE_PIXELS:  # 3
                    raise TooManyPixelsError(f"{width}×{height}")
                animated = getattr(image, "n_frames", 1) > 1
                image.verify()
    except Image.DecompressionBombError as exc:
        # SECURITY: a tiny file can declare a huge size (Pillow refuses above ~179 MP at open);
        # it is the same refusal as too many pixels, never a 500.
        raise TooManyPixelsError("declared size far above the limit") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        if isinstance(exc, TooManyPixelsError):
            raise
        raise NotAnImageError("This image file is damaged or isn't what it claims to be.") from exc
    if animated:
        raise NotAnImageError("Animated images aren't supported. Upload a still photo.")
    return ImageInfo(format=image_format, width=width, height=height)


def detect_direct_format(head: bytes) -> str | None:
    """pdf | mp4 | mov | webm from the first bytes (fake store only; Cloudinary does its own)."""
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    brands = _ftyp_brands(head)
    if brands is not None:
        return "mov" if brands[0] == b"qt  " else "mp4"
    return None
