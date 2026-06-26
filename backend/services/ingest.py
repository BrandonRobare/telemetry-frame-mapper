from __future__ import annotations

import os
import re
from datetime import datetime

import piexif
from PIL import Image


def _rational_to_float(rational) -> float:
    """Convert EXIF rational to float. Handles GPS coord triplets and single rationals."""
    if isinstance(rational, (list, tuple)) and len(rational) == 3:
        d = rational[0][0] / rational[0][1]
        m = rational[1][0] / rational[1][1]
        s = rational[2][0] / rational[2][1]
        return d + m / 60 + s / 3600
    if isinstance(rational, tuple) and len(rational) == 2:
        return rational[0] / rational[1] if rational[1] != 0 else 0.0
    return 0.0


def _extract_xmp_dji(filepath: str) -> dict:
    """Read DJI XMP metadata from a JPEG file.

    Parses RelativeAltitude (AGL), FlightYawDegree, and GimbalPitchDegree
    from the raw XMP block embedded near the start of the file.
    Returns a dict with whichever keys were found.
    """
    try:
        with open(filepath, "rb") as f:
            data = f.read(131072)  # XMP is always in the first 128 KB
    except OSError:
        return {}
    result: dict = {}
    
    # Support various XMP variants including:
    # 1. Quoted attributes (legacy): RelativeAltitude="123"
    # 2. Namespace-prefixed: drone-dji:RelativeAltitude="123"
    # 3. Unquoted values: RelativeAltitude=123
    # 4. XML format with tags: <drone-dji:RelativeAltitude>123</drone-dji:RelativeAltitude>
    
    for key, patterns in (
        ("altitude_m", (
            rb'RelativeAltitude="([+-]?\d+\.?\d*)"',
            rb'drone-dji:RelativeAltitude="([+-]?\d+\.?\d*)"',
            rb'RelativeAltitude=([+-]?\d+\.?\d*)',
            rb'<drone-dji:RelativeAltitude>([+-]?\d+\.?\d*)</drone-dji:RelativeAltitude>',
        )),
        ("yaw", (
            rb'FlightYawDegree="([+-]?\d+\.?\d*)"',
            rb'drone-dji:FlightYawDegree="([+-]?\d+\.?\d*)"',
            rb'FlightYawDegree=([+-]?\d+\.?\d*)',
            rb'<drone-dji:FlightYawDegree>([+-]?\d+\.?\d*)</drone-dji:FlightYawDegree>',
        )),
        ("gimbal_pitch", (
            rb'GimbalPitchDegree="([+-]?\d+\.?\d*)"',
            rb'drone-dji:GimbalPitchDegree="([+-]?\d+\.?\d*)"',
            rb'GimbalPitchDegree=([+-]?\d+\.?\d*)',
            rb'<drone-dji:GimbalPitchDegree>([+-]?\d+\.?\d*)</drone-dji:GimbalPitchDegree>',
        )),
    ):
        for pattern in patterns:
            m = re.search(pattern, data)
            if m:
                try:
                    result[key] = float(m.group(1))
                except ValueError:
                    pass
                break # Found match, move to next key
    return result


def extract_exif(filepath: str) -> dict:
    """Extract metadata from a JPEG file.

    Returns dict with: filename, filepath, timestamp, latitude, longitude,
    altitude_m, gps_source, yaw, gimbal_pitch, width, height, focal_length_mm.
    """
    result = {
        "filename": os.path.basename(filepath),
        "filepath": os.path.abspath(filepath),
        "timestamp": None,
        "latitude": None,
        "longitude": None,
        "altitude_m": None,
        "gps_source": "none",
        "yaw": None,
        "gimbal_pitch": None,
        "width": None,
        "height": None,
        "focal_length_mm": None,
    }

    try:
        with Image.open(filepath) as img:
            result["width"], result["height"] = img.size
            exif_bytes = img.info.get("exif")
    except Exception:
        return result

    if not exif_bytes:
        return result

    try:
        exif = piexif.load(exif_bytes)
    except Exception:
        return result

    dt_str = exif.get("Exif", {}).get(piexif.ExifIFD.DateTimeOriginal)
    if dt_str:
        try:
            result["timestamp"] = datetime.strptime(dt_str.decode(), "%Y:%m:%d %H:%M:%S")
        except Exception:
            pass

    fl = exif.get("Exif", {}).get(piexif.ExifIFD.FocalLength)
    if fl:
        result["focal_length_mm"] = _rational_to_float(fl)

    gps = exif.get("GPS", {})
    if gps:
        lat_ref = gps.get(piexif.GPSIFD.GPSLatitudeRef, b"N")
        lon_ref = gps.get(piexif.GPSIFD.GPSLongitudeRef, b"E")
        lat_raw = gps.get(piexif.GPSIFD.GPSLatitude)
        lon_raw = gps.get(piexif.GPSIFD.GPSLongitude)
        alt_raw = gps.get(piexif.GPSIFD.GPSAltitude)

        if lat_raw and lon_raw:
            lat = _rational_to_float(lat_raw)
            lon = _rational_to_float(lon_raw)
            if lat_ref == b"S":
                lat = -lat
            if lon_ref == b"W":
                lon = -lon
            result["latitude"] = lat
            result["longitude"] = lon
            result["gps_source"] = "exif"

        if alt_raw:
            result["altitude_m"] = _rational_to_float(alt_raw)

    xmp = _extract_xmp_dji(filepath)
    if "altitude_m" in xmp:
        result["altitude_m"] = xmp["altitude_m"]
    if "yaw" in xmp:
        result["yaw"] = xmp["yaw"]
    if "gimbal_pitch" in xmp:
        result["gimbal_pitch"] = xmp["gimbal_pitch"]

    return result


def generate_thumbnail(src_path: str, dest_path: str, size: int = 200) -> None:
    """Generate a thumbnail JPEG preserving aspect ratio. Max dimension = size px."""
    try:
        from backend.core.config import get_ingest_config

        quality = int(get_ingest_config().get("thumbnail_jpeg_quality", 75))
    except Exception:  # pragma: no cover
        quality = 75
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    with Image.open(src_path) as img:
        img.thumbnail((size, size), Image.LANCZOS)
        img.save(dest_path, "JPEG", quality=quality)
