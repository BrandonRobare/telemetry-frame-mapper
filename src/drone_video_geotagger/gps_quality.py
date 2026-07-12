"""Cheap GPS-lock heuristics over parsed telemetry.

These checks flag telemetry that suggests the GPS receiver had a weak or
missing satellite lock during capture:

- points sitting at (0, 0) — "Null Island" placeholder fixes,
- coordinates frozen across many consecutive points (a receiver repeating
  its last fix), and
- implausible position jumps between consecutive points (speed-based when
  timestamps are available, distance-based otherwise).

Satellite counts are not part of the parsed DJI SRT shape, so they are not
checked here.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from math import cos, hypot, radians

from drone_video_geotagger.telemetry import TelemetryPoint

NEAR_ZERO_DEGREES = 0.001
"""Points within ~111 m of (0, 0) are treated as no-fix placeholders."""

FROZEN_MIN_RUN = 10
"""Consecutive identical fixes before the frozen-coordinates warning fires."""

MAX_PLAUSIBLE_SPEED_MS = 60.0
"""Generous speed ceiling (m/s) for consumer drones; ~216 km/h."""

MAX_PLAUSIBLE_STEP_M = 500.0
"""Distance ceiling between consecutive points when timing is unknown."""

_MIN_SPEED_DT_S = 0.2
_METERS_PER_DEGREE = 111_320.0


@dataclass(frozen=True)
class GpsSample:
    """One GPS fix: latitude/longitude plus an optional capture time."""

    lat: float
    lon: float
    t_s: float | None = None


@dataclass(frozen=True)
class GpsLockReport:
    sample_count: int
    near_zero_count: int
    longest_frozen_run: int
    jump_count: int
    max_speed_ms: float | None
    warnings: tuple[str, ...]


def samples_from_telemetry(points: Sequence[TelemetryPoint]) -> list[GpsSample]:
    return [GpsSample(lat=point.lat, lon=point.lon, t_s=point.start_s) for point in points]


def _is_near_zero(sample: GpsSample) -> bool:
    return abs(sample.lat) <= NEAR_ZERO_DEGREES and abs(sample.lon) <= NEAR_ZERO_DEGREES


def _distance_m(a: GpsSample, b: GpsSample) -> float:
    mid_lat = radians((a.lat + b.lat) / 2.0)
    dlat_m = (b.lat - a.lat) * _METERS_PER_DEGREE
    dlon_m = (b.lon - a.lon) * _METERS_PER_DEGREE * cos(mid_lat)
    return hypot(dlat_m, dlon_m)


def assess_gps_lock(samples: Iterable[GpsSample]) -> GpsLockReport:
    """Run all GPS-lock heuristics over ``samples`` (in capture order)."""
    items = list(samples)
    sample_count = len(items)

    near_zero_count = sum(1 for sample in items if _is_near_zero(sample))

    longest_frozen_run = 1 if items else 0
    current_run = longest_frozen_run
    for previous, current in zip(items, items[1:], strict=False):
        if current.lat == previous.lat and current.lon == previous.lon:
            current_run += 1
            longest_frozen_run = max(longest_frozen_run, current_run)
        else:
            current_run = 1

    # Jump detection only considers pairs of valid (non near-zero) fixes so a
    # receiver acquiring its first fix is not double-reported as a jump.
    jump_count = 0
    max_speed_ms: float | None = None
    for previous, current in zip(items, items[1:], strict=False):
        if _is_near_zero(previous) or _is_near_zero(current):
            continue
        distance_m = _distance_m(previous, current)
        dt = None
        if previous.t_s is not None and current.t_s is not None:
            dt = current.t_s - previous.t_s
        if dt is not None and dt >= _MIN_SPEED_DT_S:
            speed = distance_m / dt
            if max_speed_ms is None or speed > max_speed_ms:
                max_speed_ms = speed
            if speed > MAX_PLAUSIBLE_SPEED_MS:
                jump_count += 1
        elif distance_m > MAX_PLAUSIBLE_STEP_M:
            jump_count += 1

    warnings: list[str] = []
    if near_zero_count:
        warnings.append(
            f"{near_zero_count} of {sample_count} GPS points sit at (0, 0); the receiver "
            "likely had no satellite fix for part of the capture."
        )
    if longest_frozen_run >= FROZEN_MIN_RUN:
        warnings.append(
            f"GPS coordinates are frozen across {longest_frozen_run} consecutive points; "
            "the receiver may have lost lock and repeated its last fix."
        )
    if jump_count:
        warnings.append(
            f"{jump_count} implausible position jump(s) between consecutive GPS points; "
            "positions may be unreliable."
        )

    return GpsLockReport(
        sample_count=sample_count,
        near_zero_count=near_zero_count,
        longest_frozen_run=longest_frozen_run,
        jump_count=jump_count,
        max_speed_ms=max_speed_ms,
        warnings=tuple(warnings),
    )
