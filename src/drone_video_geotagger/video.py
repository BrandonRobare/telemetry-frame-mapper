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
                "0:2",
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
    match = re.search(r"creation_time\s*:\s*([0-9T:\.\-]+Z)", text)
    if not match:
        return None
    return datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
