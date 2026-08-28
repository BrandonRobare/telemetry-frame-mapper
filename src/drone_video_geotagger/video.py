from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path

from drone_video_geotagger.paths import external_file_arg


def extract_srt(ffmpeg: str | Path, video: Path, srt_path: Path) -> None:
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [
                str(ffmpeg),
                "-y",
                "-hide_banner",
                "-i",
                external_file_arg(video, ffmpeg),
                "-map",
                "0:s:0",
                "-f",
                "srt",
                external_file_arg(srt_path, ffmpeg),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"ffmpeg executable not found: {ffmpeg}. "
            "Install ffmpeg or pass --ffmpeg /path/to/ffmpeg."
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg could not extract SRT metadata:\n{result.stderr}")


def read_video_duration(ffmpeg: str | Path, video: Path) -> float | None:
    try:
        result = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-i", external_file_arg(video, ffmpeg)],
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"ffmpeg executable not found: {ffmpeg}. "
            "Install ffmpeg or pass --ffmpeg /path/to/ffmpeg."
        ) from exc
    text = result.stdout + "\n" + result.stderr
    match = re.search(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)", text)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def read_video_start(ffmpeg: str | Path, video: Path) -> datetime | None:
    try:
        result = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-i", external_file_arg(video, ffmpeg)],
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"ffmpeg executable not found: {ffmpeg}. "
            "Install ffmpeg or pass --ffmpeg /path/to/ffmpeg."
        ) from exc
    text = result.stdout + "\n" + result.stderr
    # Accept optional Z or numeric offset (+HH:MM, -HH:MM, +HHMM, -HHMM).
    # Bare timestamps without any suffix are treated as UTC. Match the time of
    # day explicitly so a negative offset cannot be consumed as part of it.
    match = re.search(
        r"creation_time\s*:\s*([0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9:.]+)"
        r"(Z|[+-]\d{2}:?\d{2})?",
        text,
    )
    if not match:
        if re.search(r"creation_time\s*:", text):
            raise ValueError("ffmpeg reported a creation_time without a time of day")
        return None
    ts = match.group(1)
    suffix = match.group(2)
    if suffix == "Z" or suffix is None:
        ts = ts + "+00:00"
    else:
        if ":" not in suffix:
            # +HHMM → +HH:MM
            suffix = suffix[:3] + ":" + suffix[3:]
        ts = ts + suffix
    return datetime.fromisoformat(ts)
