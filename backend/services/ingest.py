from __future__ import annotations

import os
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

    return result


def generate_thumbnail(src_path: str, dest_path: str, size: int = 200) -> None:
    """Generate a thumbnail JPEG preserving aspect ratio. Max dimension = size px."""
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    with Image.open(src_path) as img:
        img.thumbnail((size, size), Image.LANCZOS)
        img.save(dest_path, "JPEG", quality=75)
