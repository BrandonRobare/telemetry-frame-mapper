from __future__ import annotations

import os
import tempfile

import piexif
import pytest
from PIL import Image

from backend.services.ingest import extract_exif, generate_thumbnail


def make_gps_jpeg(lat: float, lon: float, alt_m: float, out_path: str):
    """Create a minimal JPEG with GPS EXIF at given coords."""
    img = Image.new("RGB", (100, 100), color=(100, 150, 200))

    def to_rational(value: float):
        d = int(abs(value))
        m = int((abs(value) - d) * 60)
        s = round(((abs(value) - d) * 60 - m) * 60 * 100)
        return ((d, 1), (m, 1), (s, 100))

    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: b"N" if lat >= 0 else b"S",
        piexif.GPSIFD.GPSLatitude: to_rational(lat),
        piexif.GPSIFD.GPSLongitudeRef: b"E" if lon >= 0 else b"W",
        piexif.GPSIFD.GPSLongitude: to_rational(abs(lon)),
        piexif.GPSIFD.GPSAltitude: (int(alt_m * 100), 100),
        piexif.GPSIFD.GPSAltitudeRef: 0,
    }
    exif_dict = {"GPS": gps_ifd}
    exif_bytes = piexif.dump(exif_dict)
    img.save(out_path, "JPEG", exif=exif_bytes)


def test_extract_exif_with_gps():
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    make_gps_jpeg(41.153, -81.341, 60.96, path)
    data = extract_exif(path)
    assert data["latitude"] == pytest.approx(41.153, abs=0.001)
    assert data["longitude"] == pytest.approx(-81.341, abs=0.001)
    assert data["altitude_m"] == pytest.approx(60.96, abs=0.5)
    assert data["gps_source"] == "exif"
    os.unlink(path)


def test_extract_exif_no_gps():
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img = Image.new("RGB", (100, 100))
    img.save(path, "JPEG")
    data = extract_exif(path)
    assert data["latitude"] is None
    assert data["gps_source"] == "none"
    os.unlink(path)


def test_generate_thumbnail_creates_file():
    fd, src = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img = Image.new("RGB", (400, 300), color=(200, 100, 50))
    img.save(src, "JPEG")

    fd2, thumb = tempfile.mkstemp(suffix=".jpg")
    os.close(fd2)
    generate_thumbnail(src, thumb, size=200)

    assert os.path.exists(thumb)
    with Image.open(thumb) as t:
        assert max(t.size) <= 200
    os.unlink(src)
    os.unlink(thumb)
