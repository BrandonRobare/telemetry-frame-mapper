from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from drone_video_geotagger.telemetry import TelemetryPoint, interpolate, resolve_altitudes

# The number ffmpeg's image2 muxer gives the first frame it writes unless it is run with
# `-start_number` (the documented `ffmpeg -i flight.mp4 -vf fps=8 frame_%05d.jpg` writes
# frame_00001.jpg first). Frame N was taken (N - start number) / fps seconds into the video.
DEFAULT_START_NUMBER = 1


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
    for path in frame_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg"}:
            continue
        # Frame index = the LAST number in the filename, so prefixed names like
        # DJI_0081_frame_42.jpg index as 42, not 81. Files without digits skipped.
        digit_groups = re.findall(r"\d+", path.stem)
        if digit_groups:
            frames.append((path, int(digit_groups[-1])))
    if not frames:
        raise ValueError(f"No .jpg/.jpeg frames found in {frame_dir}")
    # Sort by extracted frame index, not lexicographic filename order.
    # Prevents false gap-detection aborts with unpadded names like DJI_1…DJI_12.
    frames.sort(key=lambda t: t[1])
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


def check_start_number(frames: list[tuple[Path, int]], start_number: int) -> None:
    """Reject a start number that ffmpeg could not have numbered these frames from."""
    if start_number < 0:
        raise ValueError(f"start number must be zero or greater, got {start_number}")
    if frames and frames[0][1] < start_number:
        raise ValueError(
            f"Cannot time frame {frames[0][1]}: it is numbered below the start number "
            f"{start_number}. Re-run with --start-number set to the number of the first "
            "frame ffmpeg wrote (its -start_number, 1 unless you passed one)."
        )


def infer_frame_rate(
    frames: list[tuple[Path, int]],
    telemetry_end_s: float,
    video_duration_s: float | None = None,
    start_number: int = DEFAULT_START_NUMBER,
) -> float:
    check_start_number(frames, start_number)
    gap_summary = frame_numbering_gap_summary(frames)
    if gap_summary:
        raise ValueError(
            "Cannot safely infer frame rate from non-contiguous frame numbering "
            f"({gap_summary}). Re-run with --frame-rate set to the extraction rate."
        )

    # Deleted leading frames (the take-off) are a gap too: counting only the survivors
    # would under-estimate the rate and misplace every frame.
    first_index = frames[0][1]
    if first_index > start_number:
        missing = first_index - start_number
        plural = "" if missing == 1 else "s"
        raise ValueError(
            "Cannot safely infer frame rate: numbering starts at "
            f"{start_number} but the first frame is {first_index} (missing {missing} frame "
            f"number{plural}). Re-run with --frame-rate set to the extraction rate, or with "
            f"--start-number {first_index} if ffmpeg numbered the frames from {first_index}."
        )

    if telemetry_end_s <= 0:
        raise ValueError(
            "Cannot infer frame rate: the telemetry reports no duration "
            f"(it ends at {telemetry_end_s:g} s). Re-run with --frame-rate set to the "
            "extraction rate."
        )

    rough_rate = len(frames) / telemetry_end_s
    frame_rate = rough_rate
    for candidate in (1, 2, 4, 5, 8, 10, 12, 15, 24, 25, 29.97, 30):
        if math.isclose(rough_rate, candidate, rel_tol=0.015, abs_tol=0.05):
            frame_rate = float(candidate)
            break

    if video_duration_s and video_duration_s > 0:
        implied_span_s = (frames[-1][1] - frames[0][1]) / frame_rate
        if not math.isclose(implied_span_s, video_duration_s, rel_tol=0.03, abs_tol=0.05):
            raise ValueError(
                "Cannot safely infer frame rate: the frame-number span "
                f"({implied_span_s:g} s) disagrees with the video duration "
                f"({video_duration_s:g} s) while telemetry ends at {telemetry_end_s:g} s. "
                "Re-run with --frame-rate set to the extraction rate."
            )
    return frame_rate


def build_frame_tags(
    frames: list[tuple[Path, int]],
    telemetry: list[TelemetryPoint],
    output_dir: Path,
    frame_rate: float,
    takeoff_altitude_m: float,
    video_start: datetime | None,
    in_place: bool = False,
    start_number: int = DEFAULT_START_NUMBER,
) -> list[FrameTag]:
    if frame_rate <= 0:
        raise ValueError("frame rate must be greater than zero")
    check_start_number(frames, start_number)

    # The only place a launch elevation is known, so the only place an absolute-only
    # altitude can be converted to height above launch.
    telemetry = resolve_altitudes(telemetry, takeoff_altitude_m)

    tags: list[FrameTag] = []

    for source, frame_index in frames:
        # Measured from ffmpeg's start number, never from the first frame that survived:
        # a frame's time depends only on its own number, so deleting frames moves no other.
        seconds = (frame_index - start_number) / frame_rate
        if seconds >= telemetry[-1].end_s:
            raise ValueError(
                f"Cannot geotag frame {frame_index} at {seconds:g}s: telemetry ends at "
                f"{telemetry[-1].end_s:g}s. Re-run with complete telemetry or exclude frames "
                "outside its recorded span (or set --start-number if ffmpeg did not number "
                f"the frames from {start_number})."
            )
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
