"""Remove embedded metadata (EXIF with GPS, XMP, IPTC, comments, text chunks) and anything
hidden after the image from a checked photo before it goes to any store.

Collaborators: uploads.checked_photo (after sniff.inspect_image, before the store upload); both
stores receive only the cleaned bytes.
Implements: SECURITY.md §6 (photos), D-033.

How it works:
  1. Read the file's own structure (JPEG segments and scans, PNG chunks, WebP RIFF chunks) to
     find where the image really ends and whether anything but pixels and the colour profile is
     inside. AVIF isn't read this way; it is always re-encoded.
  2. Nothing extra inside → keep the bytes, cut at the image's real end (JPEG EOI, PNG IEND,
     the WebP RIFF size). A file with nothing after it passes through unchanged (no needless
     re-encoding, so no quality loss).
  3. Otherwise decode, apply the EXIF orientation (ImageOps.exif_transpose), and re-encode in the
     same format with a fresh, empty `info`, keeping only the ICC colour profile.
  4. Report the size of the transposed image (a portrait photo stored as landscape + an
     orientation tag comes out portrait).

SECURITY / COMPLIANCE: phone photos carry GPS coordinates, device serials and timestamps in
EXIF/XMP. Cloudinary strips metadata only from *transformed* deliveries; the stored original
keeps it, and anyone can drop the transformation from a delivery URL to fetch that original.
Bytes appended after the image (HTML, script, a ZIP) would be stored and served too. So both
are removed here, on the server, for every photo, whatever the browser did. Unknown chunks
count as metadata (allow-list, not block-list). The ICC profile is kept on purpose: it
describes colours, not people or places, and dropping it would shift colours on wide-gamut
photos. Don't loosen this without owner approval.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Final

from PIL import Image, ImageOps

from empire_api.media.sniff import PILLOW_FORMATS, ImageInfo

JPEG_QUALITY: Final = 90
LOSSY_QUALITY: Final = 90
# JPEG markers that are fine to keep: APP0 (JFIF), APP14 (Adobe colour transform). APP2 is
# fine only when it is the ICC profile; any other APPn (EXIF/XMP in APP1, MPF in APP2, IPTC
# in APP13, …) or a COM comment counts as metadata.
_JPEG_HARMLESS: Final = frozenset({0xE0, 0xEE})
# Chunks that only describe pixels or colour; anything else (text, EXIF, time, private chunks)
# counts as metadata.
_PNG_PIXELS: Final = frozenset(
    {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"iCCP", b"sBIT"}
    | {b"pHYs", b"bKGD"}
)
_WEBP_PIXELS: Final = frozenset({b"VP8 ", b"VP8L", b"VP8X", b"ALPH", b"ICCP"})


@dataclass(frozen=True)
class CleanImage:
    data: bytes
    info: ImageInfo
    changed: bool


@dataclass(frozen=True)
class Layout:
    """Where the image really ends, and whether it carries anything but pixels and colour."""

    end: int
    metadata: bool


def strip_metadata(data: bytes, info: ImageInfo) -> CleanImage:
    """The photo without metadata or trailing bytes (steps 1–4 in the module header)."""
    layout = _layout(data, info.format)  # 1
    if layout is not None and not layout.metadata:  # 2
        if layout.end == len(data):
            return CleanImage(data=data, info=info, changed=False)
        return CleanImage(data=data[: layout.end], info=info, changed=True)
    return _reencode(data, info)


def has_metadata(data: bytes, image_format: str) -> bool:
    """Whether the file carries anything beyond pixels and its colour profile (or can't tell)."""
    layout = _layout(data, image_format)
    return layout is None or layout.metadata


def _reencode(data: bytes, info: ImageInfo) -> CleanImage:
    with Image.open(io.BytesIO(data), formats=[PILLOW_FORMATS[info.format]]) as original:
        icc_profile = original.info.get("icc_profile")
        upright = ImageOps.exif_transpose(original)  # 3
    # Only pixel data survives: a palette PNG's transparent colour is part of the picture.
    upright.info = {k: v for k, v in upright.info.items() if k == "transparency"}
    out = io.BytesIO()
    options = _save_options(info.format, icc_profile, data)
    upright.save(out, format=PILLOW_FORMATS[info.format], **options)
    width, height = upright.size  # 4
    return CleanImage(
        data=out.getvalue(),
        info=ImageInfo(format=info.format, width=width, height=height),
        changed=True,
    )


def _save_options(image_format: str, icc_profile: bytes | None, data: bytes) -> dict[str, Any]:
    options: dict[str, Any] = {"icc_profile": icc_profile} if icc_profile else {}
    if image_format == "jpg":
        return {**options, "quality": JPEG_QUALITY, "optimize": True, "progressive": True}
    if image_format == "webp":
        lossless = b"VP8L" in _webp_chunks(data)  # keep a lossless WebP lossless
        return {**options, "lossless": lossless, "quality": 100 if lossless else LOSSY_QUALITY}
    if image_format == "avif":
        return {**options, "quality": LOSSY_QUALITY}
    return {**options, "optimize": True}  # png: lossless anyway


def _layout(data: bytes, image_format: str) -> Layout | None:
    """None when the structure can't be read with confidence (then the file is re-encoded)."""
    if image_format == "jpg":
        return _jpeg_layout(data)
    if image_format == "png":
        return _png_layout(data)
    if image_format == "webp":
        return _webp_layout(data)
    return None  # AVIF: always re-encoded


# --- JPEG ------------------------------------------------------------------------------------


def _jpeg_layout(data: bytes) -> Layout | None:
    """Walk every segment and scan (progressive files have several) up to EOI."""
    position, metadata = 2, False  # after SOI
    while position + 2 <= len(data):
        if data[position] != 0xFF:
            return None
        marker = data[position + 1]
        if marker == 0xFF:  # fill byte
            position += 1
            continue
        if marker == 0xD9:  # EOI: the image ends here
            return Layout(end=position + 2, metadata=metadata)
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:  # markers without a length
            position += 2
            continue
        if position + 4 > len(data):
            return None
        length = int.from_bytes(data[position + 2 : position + 4], "big")
        segment = data[position + 4 : position + 2 + length]
        metadata = metadata or _jpeg_segment_is_metadata(marker, segment)
        position += 2 + length
        if marker == 0xDA:  # SOS: entropy-coded data follows until the next real marker
            found = _jpeg_next_marker(data, position)
            if found is None:
                return None
            position = found
    return None


def _jpeg_segment_is_metadata(marker: int, segment: bytes) -> bool:
    if marker == 0xFE:  # COM
        return True
    is_icc = marker == 0xE2 and segment.startswith(b"ICC_PROFILE\x00")
    return 0xE0 <= marker <= 0xEF and marker not in _JPEG_HARMLESS and not is_icc


def _jpeg_next_marker(data: bytes, position: int) -> int | None:
    """Skip scan data: FF00 is a stuffed byte and FFD0–FFD7 are restart markers."""
    while True:
        index = data.find(b"\xff", position)
        if index < 0 or index + 1 >= len(data):
            return None
        following = data[index + 1]
        if following == 0x00 or 0xD0 <= following <= 0xD7:
            position = index + 2
            continue
        return index


# --- PNG and WebP ------------------------------------------------------------------------------


def _png_layout(data: bytes) -> Layout | None:
    position, metadata = 8, False  # after the signature
    while position + 12 <= len(data):
        length = int.from_bytes(data[position : position + 4], "big")
        kind = data[position + 4 : position + 8]
        end = position + 12 + length
        if end > len(data):
            return None
        metadata = metadata or kind not in _PNG_PIXELS
        if kind == b"IEND":
            return Layout(end=end, metadata=metadata)
        position = end
    return None


def _png_chunks(data: bytes) -> set[bytes]:
    chunks: set[bytes] = set()
    position = 8
    while position + 8 <= len(data):
        length = int.from_bytes(data[position : position + 4], "big")
        kind = data[position + 4 : position + 8]
        chunks.add(kind)
        if kind == b"IEND":
            break
        position += 12 + length
    return chunks


def _webp_layout(data: bytes) -> Layout | None:
    """The RIFF size says where the file ends; anything after it is not part of the image."""
    end = 8 + int.from_bytes(data[4:8], "little")
    if not 12 <= end <= len(data):
        return None
    return Layout(end=end, metadata=bool(_webp_chunks(data[:end]) - _WEBP_PIXELS))


def _webp_chunks(data: bytes) -> set[bytes]:
    chunks: set[bytes] = set()
    position = 12  # after "RIFF" <size> "WEBP"
    while position + 8 <= len(data):
        kind = data[position : position + 4]
        length = int.from_bytes(data[position + 4 : position + 8], "little")
        chunks.add(kind)
        position += 8 + length + (length & 1)
    return chunks
