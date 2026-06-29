from __future__ import annotations

import bisect
import csv
import io
from dataclasses import dataclass
from datetime import timezone
from typing import Any


@dataclass(frozen=True)
class InterpolatedLogPoint:
    timestamp_s: float
    latitude: float
    longitude: float
    altitude_m: float | None
    before_timestamp_s: float
    after_timestamp_s: float
    interpolation_ratio: float
    nearest_delta_s: float


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
    return sorted(points, key=lambda p: p["timestamp_s"])


def _image_timestamp_s(timestamp: Any) -> float:
    """Return a stable Unix timestamp for image datetimes.

    Naive datetimes in this app are stored as UTC. ``datetime.timestamp()``
    interprets naive datetimes in local time, so attach UTC first.
    """
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc).timestamp()
    return timestamp.timestamp()


def _lerp_optional(a: float | None, b: float | None, ratio: float) -> float | None:
    if a is None or b is None:
        return a if ratio <= 0.5 else b
    return a + (b - a) * ratio


def _lerp_required(a: float, b: float, ratio: float) -> float:
    return a + (b - a) * ratio


def interpolate_log_point(
    log_points: list[dict],
    timestamp_s: float,
    tolerance_s: float,
) -> InterpolatedLogPoint | None:
    """Interpolate a log point at ``timestamp_s``.

    Points inside the log timeline use linear interpolation. Points just outside
    the timeline are accepted only within ``tolerance_s`` and clamp to the edge
    point. ``nearest_delta_s`` reports distance to the closest raw log sample;
    this is useful for previewing whether sample spacing and offset are sane.
    """
    if not log_points:
        return None

    points = sorted(log_points, key=lambda p: p["timestamp_s"])
    times = [float(p["timestamp_s"]) for p in points]
    idx = bisect.bisect_left(times, timestamp_s)

    if idx == 0:
        delta = times[0] - timestamp_s
        if abs(delta) > tolerance_s:
            return None
        point = points[0]
        return InterpolatedLogPoint(
            timestamp_s=times[0],
            latitude=point["latitude"],
            longitude=point["longitude"],
            altitude_m=point.get("altitude_m"),
            before_timestamp_s=times[0],
            after_timestamp_s=times[0],
            interpolation_ratio=0.0,
            nearest_delta_s=delta,
        )

    if idx >= len(points):
        delta = times[-1] - timestamp_s
        if abs(delta) > tolerance_s:
            return None
        point = points[-1]
        return InterpolatedLogPoint(
            timestamp_s=times[-1],
            latitude=point["latitude"],
            longitude=point["longitude"],
            altitude_m=point.get("altitude_m"),
            before_timestamp_s=times[-1],
            after_timestamp_s=times[-1],
            interpolation_ratio=1.0,
            nearest_delta_s=delta,
        )

    before = points[idx - 1]
    after = points[idx]
    t0 = times[idx - 1]
    t1 = times[idx]
    span = t1 - t0
    ratio = 0.0 if span <= 0 else (timestamp_s - t0) / span
    if abs(timestamp_s - t0) <= abs(t1 - timestamp_s):
        nearest_delta = t0 - timestamp_s
    else:
        nearest_delta = t1 - timestamp_s

    return InterpolatedLogPoint(
        timestamp_s=timestamp_s,
        latitude=_lerp_required(before["latitude"], after["latitude"], ratio),
        longitude=_lerp_required(before["longitude"], after["longitude"], ratio),
        altitude_m=_lerp_optional(before.get("altitude_m"), after.get("altitude_m"), ratio),
        before_timestamp_s=t0,
        after_timestamp_s=t1,
        interpolation_ratio=ratio,
        nearest_delta_s=nearest_delta,
    )


def match_images_to_log(
    images: list,
    log_points: list,
    tolerance_s: float,
    offset_s: float = 0.0,
) -> list[dict]:
    """Match images to flight log positions using offset-aware interpolation.

    ``offset_s`` is applied to image timestamps before looking up the log point:
    positive values mean the flight log is later than the image clock.
    """
    results = []
    for img in images:
        if img.timestamp is None:
            continue
        img_t = _image_timestamp_s(img.timestamp)
        adjusted_t = img_t + offset_s
        interpolated = interpolate_log_point(log_points, adjusted_t, tolerance_s)
        if interpolated is None:
            continue
        results.append({
            "image_id": img.id,
            "filename": img.filename,
            "image_timestamp": img_t,
            "adjusted_timestamp": round(adjusted_t, 3),
            "matched_timestamp": round(interpolated.timestamp_s, 3),
            "delta_s": round(interpolated.nearest_delta_s, 3),
            "offset_s": offset_s,
            "latitude": interpolated.latitude,
            "longitude": interpolated.longitude,
            "altitude_m": interpolated.altitude_m,
            "interpolated": interpolated.before_timestamp_s != interpolated.after_timestamp_s,
            "before_timestamp": round(interpolated.before_timestamp_s, 3),
            "after_timestamp": round(interpolated.after_timestamp_s, 3),
            "interpolation_ratio": round(interpolated.interpolation_ratio, 3),
        })
    return results


def build_offset_preview(
    images: list,
    log_points: list,
    tolerance_s: float,
    center_offset_s: float = 0.0,
    window_s: float = 10.0,
    step_s: float = 1.0,
) -> list[dict]:
    """Summarize match coverage across candidate offsets for a preview graph."""
    if step_s <= 0:
        step_s = 1.0
    steps = int((window_s * 2) / step_s)
    rows = []
    for i in range(steps + 1):
        offset = center_offset_s - window_s + i * step_s
        matches = match_images_to_log(images, log_points, tolerance_s=tolerance_s, offset_s=offset)
        deltas = [abs(m["delta_s"]) for m in matches if m["delta_s"] is not None]
        rows.append({
            "offset_s": round(offset, 3),
            "matched": len(matches),
            "total": len([img for img in images if img.timestamp is not None]),
            "mean_abs_delta_s": round(sum(deltas) / len(deltas), 3) if deltas else None,
        })
    return rows
