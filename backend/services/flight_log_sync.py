from __future__ import annotations

import csv
import io


def parse_dji_csv(content: bytes) -> list[dict]:
    """Parse DJI flight log CSV. Returns list of {timestamp_s, latitude, longitude, altitude_m}."""
    reader = csv.DictReader(io.StringIO(content.decode()))
    points = []
    for row in reader:
        try:
            ts = float(row.get("time(millisecond)", 0)) / 1000.0
            points.append({
                "timestamp_s": ts,
                "latitude": float(row["OSD.latitude"]),
                "longitude": float(row["OSD.longitude"]),
                "altitude_m": float(row.get("OSD.altitude[m]", 0)),
            })
        except (KeyError, ValueError):
            continue
    return points


def match_images_to_log(images: list, log_points: list, tolerance_s: float) -> list[dict]:
    """Match each image's timestamp to nearest log point within tolerance."""
    results = []
    for img in images:
        if img.timestamp is None:
            continue
        img_t = img.timestamp.timestamp()
        best = min(log_points, key=lambda p: abs(p["timestamp_s"] - img_t), default=None)
        if best and abs(best["timestamp_s"] - img_t) <= tolerance_s:
            results.append({
                "image_id": img.id,
                "filename": img.filename,
                "matched_timestamp": best["timestamp_s"],
                "delta_s": round(best["timestamp_s"] - img_t, 3),
                "latitude": best["latitude"],
                "longitude": best["longitude"],
                "altitude_m": best["altitude_m"],
            })
    return results
