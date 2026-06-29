from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from drone_video_geotagger.telemetry import TelemetryPoint, interpolate


@dataclass(frozen=True)
class FrameTag:
    source: Path
    target: Path
    frame_index: int
    seconds: float
    lat: float
    lon: float
    rel_alt_m: float
    abs_alt_m: float
    timestamp: datetime | None


def collect_frames(frame_dir: Path) -> list[tuple[Path, int]]:
    frames = []
    for path in sorted(
        (p for p in frame_dir.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"}),
        key=lambda p: p.name.lower(),
    ):
        # Frame index = the LAST number in the filename, so prefixed names like
        # DJI_0081_frame_42.jpg index as 42, not 81. Files without digits are skipped.
        digit_groups = re.findall(r"\d+", path.stem)
        if digit_groups:
            frames.append((path, int(digit_groups[-1])))
    if not frames:
        raise ValueError(f"No .jpg/.jpeg frames found in {frame_dir}")
    return frames


def frame_numbering_gap_summary(frames: list[tuple[Path, int]]) -> str | None:
    """Return a short gap summary when frame numbering is not contiguous."""
    if len(frames) < 2:
        return None

    previous = frames[0][1]
    for _, current in frames[1:]:
        if current <= previous:
            previous = current
            continue
        if current - previous != 1:
            missing = current - previous - 1
            plural = "" if missing == 1 else "s"
            return f"missing {missing} frame number{plural} between {previous} and {current}"
        previous = current
    return None


def infer_frame_rate(frames: list[tuple[Path, int]], telemetry_end_s: float) -> float:
    gap_summary = frame_numbering_gap_summary(frames)
    if gap_summary:
        raise ValueError(
            "Cannot safely infer frame rate from non-contiguous frame numbering "
            f"({gap_summary}). Re-run with --frame-rate set to the extraction rate."
        )

    if telemetry_end_s <= 0:
        return 8.0

    rough_rate = len(frames) / telemetry_end_s
    for candidate in (1, 2, 4, 5, 8, 10, 12, 15, 24, 25, 29.97, 30):
        if math.isclose(rough_rate, candidate, rel_tol=0.015, abs_tol=0.05):
            return float(candidate)
    return rough_rate


def build_frame_tags(
    frames: list[tuple[Path, int]],
    telemetry: list[TelemetryPoint],
    output_dir: Path,
    frame_rate: float,
    takeoff_altitude_m: float,
    video_start: datetime | None,
    in_place: bool = False,
) -> list[FrameTag]:
    if frame_rate <= 0:
        raise ValueError("frame rate must be greater than zero")

    tags: list[FrameTag] = []
    first_index = frames[0][1]

    for source, frame_index in frames:
        seconds = (frame_index - first_index) / frame_rate
        lat, lon, rel_alt_m = interpolate(telemetry, seconds)
        timestamp = video_start + timedelta(seconds=seconds) if video_start else None
        tags.append(
            FrameTag(
                source=source,
                target=source if in_place else output_dir / source.name,
                frame_index=frame_index,
                seconds=seconds,
                lat=lat,
                lon=lon,
                rel_alt_m=rel_alt_m,
                abs_alt_m=takeoff_altitude_m + rel_alt_m,
                timestamp=timestamp,
            )
        )
    return tags
