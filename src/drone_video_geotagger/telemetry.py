from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TelemetryPoint:
    start_s: float
    end_s: float
    lat: float
    lon: float
    rel_alt_m: float


def parse_srt_time(value: str) -> float:
    try:
        hours, minutes, rest = value.split(":")
        seconds, millis = rest.split(",")
        return (
            int(hours) * 3600
            + int(minutes) * 60
            + int(seconds)
            + int(millis.ljust(3, "0")[:3]) / 1000.0
        )
    except ValueError as exc:
        raise ValueError(f"Unrecognized SRT timecode: {value!r}") from exc


def parse_srt_text(text: str) -> list[TelemetryPoint]:
    time_re = re.compile(r"(\d{2}:\d{2}:\d{2},\d+)\s+-->\s+(\d{2}:\d{2}:\d{2},\d+)")
    gps_re = re.compile(
        r"GPS\s*\(\s*([+-]?\d+(?:\.\d+)?)\s*,\s*"
        r"([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*\)"
    )
    height_re = re.compile(r"(?:^|,\s*)H\s+([+-]?\d+(?:\.\d+)?)m")
    key_value_re = re.compile(
        r"\b(lat(?:itude)?|lon(?:gitude)?|rel[_\s-]?alt(?:itude)?|alt(?:itude)?)\b"
        r"\s*[:=]\s*([+-]?\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )

    points: list[TelemetryPoint] = []
    current_start = current_end = None
    timed_blocks = 0
    telemetry_like_lines = 0

    for raw_line in text.splitlines():
        line = re.sub(r"<[^<]+?>", "", raw_line).strip()
        if not line:
            current_start = current_end = None
            continue

        time_match = time_re.search(line)
        if time_match:
            current_start = parse_srt_time(time_match.group(1))
            current_end = parse_srt_time(time_match.group(2))
            timed_blocks += 1
            continue

        gps_match = gps_re.search(line)
        if gps_match and current_start is not None and current_end is not None:
            telemetry_like_lines += 1
            lon = float(gps_match.group(1))
            lat = float(gps_match.group(2))
            height_match = height_re.search(line)
            rel_alt_m = float(height_match.group(1)) if height_match else float(gps_match.group(3))
            points.append(TelemetryPoint(current_start, current_end, lat, lon, rel_alt_m))
            continue

        key_values: dict[str, float] = {}
        for key, value in key_value_re.findall(line):
            normalized = key.lower().replace(" ", "_").replace("-", "_")
            if normalized.startswith("lat"):
                key_values["lat"] = float(value)
            elif normalized.startswith("lon"):
                key_values["lon"] = float(value)
            elif normalized.startswith("rel"):
                key_values["rel_alt"] = float(value)
            elif normalized.startswith("alt"):
                key_values.setdefault("rel_alt", float(value))

        if key_values and current_start is not None and current_end is not None:
            telemetry_like_lines += 1
            lat = key_values.get("lat")
            lon = key_values.get("lon")
            rel_alt_m = key_values.get("rel_alt", 0.0)
            if lat is not None and lon is not None:
                points.append(TelemetryPoint(current_start, current_end, lat, lon, rel_alt_m))

    if len(points) < 2:
        raise ValueError(
            "Not enough GPS telemetry was found in the SRT data "
            f"(parsed {len(points)} points from {timed_blocks} timed blocks; "
            f"saw {telemetry_like_lines} telemetry-like lines). Supported DJI formats include "
            "'GPS (lon, lat, alt)' with optional 'H 12.3m', and key/value forms such as "
            "'[latitude: 41.1] [longitude: -81.1] [rel_alt: 24.0]' or "
            "'Lat: 41.1 Lon: -81.1 Alt: 24.0'."
        )
    return points


def parse_srt(srt_path: Path) -> list[TelemetryPoint]:
    try:
        return parse_srt_text(srt_path.read_text(errors="ignore"))
    except ValueError as exc:
        raise ValueError(f"{exc}: {srt_path}") from exc


def _has_gps_fix(point: TelemetryPoint) -> bool:
    return abs(point.lat) > 0.001 or abs(point.lon) > 0.001


def _no_fix_error(seconds: float) -> ValueError:
    return ValueError(f"Cannot interpolate telemetry at {seconds:g}s: no GPS fix was recorded.")


def interpolate(points: list[TelemetryPoint], seconds: float) -> tuple[float, float, float]:
    if not points:
        raise ValueError("telemetry points are required")

    for point in points:
        if point.start_s <= seconds < point.end_s and not _has_gps_fix(point):
            raise _no_fix_error(seconds)

    if seconds <= points[0].start_s:
        first = points[0]
        if not _has_gps_fix(first):
            raise _no_fix_error(seconds)
        return first.lat, first.lon, first.rel_alt_m

    for previous, current in zip(points, points[1:], strict=False):
        if seconds == current.start_s:
            if not _has_gps_fix(current):
                raise _no_fix_error(seconds)
            return current.lat, current.lon, current.rel_alt_m
        if previous.start_s < seconds < current.start_s:
            if not _has_gps_fix(previous) or not _has_gps_fix(current):
                raise _no_fix_error(seconds)
            span = current.start_s - previous.start_s
            if span <= 0:
                return previous.lat, previous.lon, previous.rel_alt_m
            ratio = (seconds - previous.start_s) / span
            lat = previous.lat + (current.lat - previous.lat) * ratio
            lon = previous.lon + (current.lon - previous.lon) * ratio
            rel_alt_m = previous.rel_alt_m + (current.rel_alt_m - previous.rel_alt_m) * ratio
            return lat, lon, rel_alt_m

    last = points[-1]
    if not _has_gps_fix(last):
        raise _no_fix_error(seconds)
    return last.lat, last.lon, last.rel_alt_m
