from __future__ import annotations

import io
import os
import random
import tempfile
from unittest.mock import patch

import piexif
import pytest
from PIL import Image

from backend.services.ingest import UnreadableImageError, extract_exif, generate_thumbnail


def make_gps_jpeg(
    lat: float,
    lon: float,
    alt_m: float,
    out_path: str,
    altitude_ref: int = 0,
):
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
        piexif.GPSIFD.GPSAltitude: (int(abs(alt_m) * 100), 100),
        piexif.GPSIFD.GPSAltitudeRef: altitude_ref,
    }
    exif_dict = {"GPS": gps_ifd}
    exif_bytes = piexif.dump(exif_dict)
    img.save(out_path, "JPEG", exif=exif_bytes)


def make_xmp_jpeg(out_path: str, xmp: bytes):
    img = Image.new("RGB", (100, 100), color=(100, 150, 200))
    exif_bytes = piexif.dump({"0th": {piexif.ImageIFD.Make: b"DJI"}})
    img.save(out_path, "JPEG", exif=exif_bytes)
    with open(out_path, "ab") as f:
        f.write(xmp)


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


def test_extract_exif_honors_below_sea_level_altitude_ref():
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    make_gps_jpeg(31.5, 35.5, 430.5, path, altitude_ref=1)
    data = extract_exif(path)
    assert data["altitude_m"] == pytest.approx(-430.5, abs=0.01)
    os.unlink(path)


def test_extract_exif_camera_lens_and_focal_metadata():
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img = Image.new("RGB", (640, 480), color=(100, 150, 200))
    exif_bytes = piexif.dump({
        "0th": {
            piexif.ImageIFD.Make: b"DJI",
            piexif.ImageIFD.Model: b"FC3582",
        },
        "Exif": {
            piexif.ExifIFD.FocalLength: (672, 100),
            piexif.ExifIFD.FocalLengthIn35mmFilm: 24,
            piexif.ExifIFD.LensModel: b"24mm F1.7",
        },
    })
    img.save(path, "JPEG", exif=exif_bytes)

    data = extract_exif(path)

    assert data["width"] == 640
    assert data["height"] == 480
    assert data["camera_make"] == "DJI"
    assert data["camera_model"] == "FC3582"
    assert data["lens_model"] == "24mm F1.7"
    assert data["focal_length_mm"] == pytest.approx(6.72)
    assert data["focal_length_35mm"] == pytest.approx(24)
    os.unlink(path)


def test_extract_exif_parses_dji_xmp_namespace_attributes():
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    make_xmp_jpeg(
        path,
        b"""
        <rdf:Description
          drone-dji:RelativeAltitude='+123.45'
          drone-dji:FlightYawDegree='-89.5'
          drone-dji:GimbalPitchDegree='-42.25' />
        """,
    )
    data = extract_exif(path)
    assert data["altitude_m"] == pytest.approx(123.45)
    assert data["yaw"] == pytest.approx(-89.5)
    assert data["gimbal_pitch"] == pytest.approx(-42.25)
    os.unlink(path)


def test_extract_exif_parses_dji_xmp_elements_and_plain_attributes():
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    make_xmp_jpeg(
        path,
        b"""
        <rdf:Description RelativeAltitude="36.0">
          <drone-dji:FlightYawDegree>179.9</drone-dji:FlightYawDegree>
          <drone-dji:GimbalPitchDegree>-90</drone-dji:GimbalPitchDegree>
        </rdf:Description>
        """,
    )
    data = extract_exif(path)
    assert data["altitude_m"] == pytest.approx(36.0)
    assert data["yaw"] == pytest.approx(179.9)
    assert data["gimbal_pitch"] == pytest.approx(-90.0)
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


def test_extract_exif_parses_dji_xmp_calibrated_focal_and_zoom():
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    make_xmp_jpeg(
        path,
        b"""
        <rdf:Description
          drone-dji:CalibratedFocalLength='24.0'
          drone-dji:DigitalZoomRatio='1.5' />
        """,
    )
    data = extract_exif(path)
    assert data["focal_length_35mm"] == pytest.approx(24.0)
    assert data["digital_zoom_ratio"] == pytest.approx(1.5)
    os.unlink(path)


def test_extract_exif_raises_unreadable_image_error_for_random_bytes(tmp_path):
    """Bytes that are not an image must raise, not come back as an empty-metadata frame."""
    path = tmp_path / "corrupt.jpg"
    path.write_bytes(random.Random(943).randbytes(2048))

    with pytest.raises(UnreadableImageError, match="cannot open image"):
        extract_exif(str(path))


def test_extract_exif_raises_unreadable_image_error_for_empty_file(tmp_path):
    path = tmp_path / "empty.jpg"
    path.write_bytes(b"")

    with pytest.raises(UnreadableImageError):
        extract_exif(str(path))


def test_extract_exif_logs_unparseable_exif_block(tmp_path):
    """A readable image with a corrupt EXIF block imports without metadata, and says so."""
    path = tmp_path / "bad_exif.jpg"
    Image.new("RGB", (64, 48)).save(path, "JPEG", exif=b"Exif\x00\x00" + b"\x13" * 40)

    with patch("backend.services.ingest.logger") as mock_logger:
        data = extract_exif(str(path))

    assert (data["width"], data["height"]) == (64, 48)
    assert data["latitude"] is None
    mock_logger.warning.assert_called_once()
    assert "bad_exif.jpg" in mock_logger.warning.call_args.args


def test_extract_exif_logs_unparseable_capture_date(tmp_path):
    path = tmp_path / "bad_date.jpg"
    exif_bytes = piexif.dump({"Exif": {piexif.ExifIFD.DateTimeOriginal: b"0000:00:00 00:00:00"}})
    Image.new("RGB", (32, 32)).save(path, "JPEG", exif=exif_bytes)

    with patch("backend.services.ingest.logger") as mock_logger:
        data = extract_exif(str(path))

    assert data["timestamp"] is None
    mock_logger.warning.assert_called_once()
    assert "bad_date.jpg" in mock_logger.warning.call_args.args


def test_generate_thumbnail_raises_unreadable_image_error_for_truncated_jpeg(tmp_path):
    """A cut-short copy parses its header but its pixel data cannot be decoded."""
    buf = io.BytesIO()
    Image.effect_noise((400, 300), 64).convert("RGB").save(buf, "JPEG")
    src = tmp_path / "truncated.jpg"
    src.write_bytes(buf.getvalue()[: len(buf.getvalue()) // 2])
    dest = tmp_path / "thumbs" / "truncated.jpg"

    with pytest.raises(UnreadableImageError, match="does not decode"):
        generate_thumbnail(str(src), str(dest), size=64)
    assert not dest.exists()


def test_generate_thumbnail_write_failure_is_not_an_unreadable_image(tmp_path):
    """Failing to write the thumbnail says nothing about the source image."""
    src = tmp_path / "ok.jpg"
    Image.new("RGB", (100, 100)).save(src, "JPEG")
    dest = tmp_path / "thumbs" / "ok.jpg"

    with patch.object(Image.Image, "save", side_effect=OSError("No space left on device")):
        with pytest.raises(OSError, match="No space left") as excinfo:
            generate_thumbnail(str(src), str(dest), size=64)
    assert not isinstance(excinfo.value, UnreadableImageError)


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
