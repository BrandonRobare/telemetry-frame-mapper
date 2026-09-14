from __future__ import annotations

import csv
from datetime import UTC
from pathlib import Path

from drone_video_geotagger.frames import FrameTag


def _csv_safe(value: object) -> str:
    """Neutralize spreadsheet formula prefixes in CSV cells (#863)."""
    text = "" if value is None else str(value)
    return ("'" + text) if text and text[0] in ("=", "+", "-", "@", "\t", "\r") else text


def write_audit_csv(tags: list[FrameTag], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "file",
                "frame_index",
                "seconds",
                "latitude",
                "longitude",
                "relative_altitude_m",
                "gps_altitude_m",
                "utc_timestamp",
            ]
        )
        for tag in tags:
            writer.writerow(
                [
                    _csv_safe(str(tag.target)),
                    tag.frame_index,
                    f"{tag.seconds:.3f}",
                    f"{tag.lat:.8f}",
                    f"{tag.lon:.8f}",
                    f"{tag.rel_alt_m:.3f}",
                    f"{tag.abs_alt_m:.3f}",
                    tag.timestamp.astimezone(UTC).isoformat() if tag.timestamp else "",
                ]
            )
