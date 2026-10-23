"""SECURITY: photos lose their embedded metadata (EXIF with GPS, XMP, IPTC, comments, PNG text)
on the server before any store sees them (media/scrub.py); files without metadata pass through
byte-identical; the EXIF orientation is applied and the ICC colour profile kept."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import ExifTags, Image, ImageCms, PngImagePlugin

from conftest import SignedIn
from empire_api.media import scrub, sniff
from media_support import fake_store, image_bytes, upload_photo
from projects_support import ok

SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def phone_exif(orientation: int = 6) -> Image.Exif:
    """EXIF as a phone writes it: orientation, camera make and a GPS position."""
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = orientation
    exif[ExifTags.Base.Make] = "PhoneCo"
    gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
    gps[ExifTags.GPS.GPSLatitudeRef] = "N"
    gps[ExifTags.GPS.GPSLatitude] = (28.0, 30.0, 0.0)
    gps[ExifTags.GPS.GPSLongitudeRef] = "E"
    gps[ExifTags.GPS.GPSLongitude] = (77.0, 18.0, 0.0)
    return exif


def landscape_red_blue() -> Image.Image:
    """40×20: left half red, right half blue (stored sideways, as phones do)."""
    image = Image.new("RGB", (40, 20), (255, 0, 0))
    image.paste((0, 0, 255), (20, 0, 40, 20))
    return image


def save(image: Image.Image, fmt: str, **options: object) -> bytes:
    out = io.BytesIO()
    image.save(out, format=fmt, **options)
    return out.getvalue()


def clean(data: bytes) -> scrub.CleanImage:
    return scrub.strip_metadata(data, sniff.inspect_image(data))


def test_jpeg_loses_gps_xmp_and_comment_and_stands_upright() -> None:
    data = save(
        landscape_red_blue(),
        "JPEG",
        exif=phone_exif(orientation=6),  # "rotate 90° clockwise to display"
        xmp=b"<x:xmpmeta><exif:GPSLatitude>28,30N</exif:GPSLatitude></x:xmpmeta>",
        comment=b"taken at home",
        icc_profile=SRGB,
    )
    assert b"PhoneCo" in data and b"taken at home" in data
    result = clean(data)
    assert result.changed
    assert (result.info.width, result.info.height) == (20, 40)  # portrait, as displayed
    with Image.open(io.BytesIO(result.data)) as out:
        assert dict(out.getexif()) == {}
        assert not out.getexif().get_ifd(ExifTags.IFD.GPSInfo)
        assert "xmp" not in out.info and "comment" not in out.info
        assert out.info.get("icc_profile") == SRGB  # colour profile kept on purpose
        assert out.size == (20, 40)
        top, bottom = out.getpixel((10, 5)), out.getpixel((10, 35))
    assert isinstance(top, tuple) and top[0] > 200 and top[2] < 60  # red on top
    assert isinstance(bottom, tuple) and bottom[2] > 200 and bottom[0] < 60
    for leak in (b"PhoneCo", b"taken at home", b"GPSLatitude", b"Exif\x00\x00"):
        assert leak not in result.data


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_a_photo_without_metadata_passes_byte_identical(fmt: str) -> None:
    """(AVIF is always re-encoded: its structure isn't read byte by byte.)"""
    data = image_bytes(fmt)
    result = clean(data)
    assert not result.changed and result.data is data


def test_a_colour_profile_alone_is_not_metadata() -> None:
    data = save(landscape_red_blue(), "JPEG", icc_profile=SRGB)
    assert clean(data).data is data


def test_png_text_chunks_and_exif_are_removed() -> None:
    text = PngImagePlugin.PngInfo()
    text.add_text("Comment", "GPS 28.5, 77.3")
    text.add_itxt("Description", "Owner's flat", zip=True)
    text.add_text("Author", "Someone", zip=True)
    image = Image.new("P", (8, 8), 1)
    image.putpalette([0, 0, 0, 255, 255, 255] + [0] * 762)
    data = save(image, "PNG", pnginfo=text, exif=phone_exif(1), transparency=0)
    result = clean(data)
    assert result.changed
    chunks = scrub._png_chunks(result.data)
    assert not chunks & {b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME"}
    assert b"GPS 28.5" not in result.data and b"Someone" not in result.data
    with Image.open(io.BytesIO(result.data)) as out:
        assert out.info.get("transparency") == 0  # pixel data, kept


def test_webp_and_avif_lose_exif_and_xmp() -> None:
    for fmt in ("WEBP", "AVIF"):
        data = save(landscape_red_blue(), fmt, exif=phone_exif(1), xmp=b"<x:xmpmeta/>")
        result = clean(data)
        assert result.changed, fmt
        with Image.open(io.BytesIO(result.data)) as out:
            assert "exif" not in out.info and "xmp" not in out.info, fmt
            assert out.format == fmt  # same format, no conversion


def test_lossless_webp_stays_lossless() -> None:
    data = save(landscape_red_blue(), "WEBP", lossless=True, exif=phone_exif(1))
    assert b"VP8L" in scrub._webp_chunks(data)
    assert b"VP8L" in scrub._webp_chunks(clean(data).data)


def test_animated_images_are_refused() -> None:
    frames = [Image.new("RGB", (8, 8), colour) for colour in ("red", "blue")]
    data = save(frames[0], "WEBP", save_all=True, append_images=frames[1:])
    with pytest.raises(sniff.NotAnImageError, match="Animated"):
        sniff.inspect_image(data)


def test_the_store_only_ever_receives_the_clean_photo(owner: SignedIn) -> None:
    data = save(landscape_red_blue(), "JPEG", exif=phone_exif(orientation=6))
    body = ok(upload_photo(owner, data, filename="IMG_0001.jpg", content_type="image/jpeg"), 201)
    assert (body["width"], body["height"]) == (20, 40)
    path = fake_store().path_for_key(body["url"].split("/dev-media/files/", 1)[1])
    assert path is not None
    stored = Path(path).read_bytes()
    assert b"PhoneCo" not in stored and b"Exif\x00\x00" not in stored
    assert body["bytes"] == len(stored)
