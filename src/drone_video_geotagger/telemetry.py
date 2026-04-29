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
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(millis.ljust(3, "0")[:3]) / 1000.0
    )


def parse_srt_text(text: str) -> list[TelemetryPoint]:
    time_re = re.compile(r"(\d{2}:\d{2}:\d{2},\d+)\s+-->\s+(\d{2}:\d{2}:\d{2},\d+)")
    gps_re = re.compile(
        r"GPS\s*\(\s*([+-]?\d+(?:\.\d+)?)\s*,\s*"
        r"([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*\)"
    )
    height_re = re.compile(r"(?:^|,\s*)H\s+([+-]?\d+(?:\.\d+)?)m")

    points: list[TelemetryPoint] = []
    current_start = current_end = None

    for raw_line in text.splitlines():
        line = re.sub(r"<[^<]+?>", "", raw_line).strip()
        if not line:
            current_start = current_end = None
            continue

        time_match = time_re.search(line)
        if time_match:
            current_start = parse_srt_time(time_match.group(1))
            current_end = parse_srt_time(time_match.group(2))
            continue

        gps_match = gps_re.search(line)
        if gps_match and current_start is not None and current_end is not None:
            lon = float(gps_match.group(1))
            lat = float(gps_match.group(2))
            height_match = height_re.search(line)
            rel_alt_m = float(height_match.group(1)) if height_match else float(gps_match.group(3))
            if lat != 0 and lon != 0:
                points.append(TelemetryPoint(current_start, current_end, lat, lon, rel_alt_m))

    if len(points) < 2:
        raise ValueError("Not enough GPS telemetry was found in the SRT data")
    return points


def parse_srt(srt_path: Path) -> list[TelemetryPoint]:
    try:
        return parse_srt_text(srt_path.read_text(errors="ignore"))
    except ValueError as exc:
        raise ValueError(f"{exc}: {srt_path}") from exc


def interpolate(points: list[TelemetryPoint], seconds: float) -> tuple[float, float, float]:
    if not points:
        raise ValueError("telemetry points are required")

    if seconds <= points[0].start_s:
        first = points[0]
        return first.lat, first.lon, first.rel_alt_m

    for previous, current in zip(points, points[1:], strict=False):
        if previous.start_s <= seconds <= current.start_s:
            span = current.start_s - previous.start_s
            if span <= 0:
                return previous.lat, previous.lon, previous.rel_alt_m
            ratio = (seconds - previous.start_s) / span
            lat = previous.lat + (current.lat - previous.lat) * ratio
            lon = previous.lon + (current.lon - previous.lon) * ratio
            rel_alt_m = previous.rel_alt_m + (current.rel_alt_m - previous.rel_alt_m) * ratio
            return lat, lon, rel_alt_m

    last = points[-1]
    return last.lat, last.lon, last.rel_alt_m
